"""初始化基础数据：可重复执行。

已存在的权限、角色、部门、字典和用户保持原样，避免覆盖界面上的修改。
只插入种子里有、库里还没有的编码。新库会得到完整的初始角色、部门和测试账号。

用法：
    uv run python -m app.seeds.initial_data
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.db import async_session_factory
from app.models.system import (
    Department,
    DictItem,
    DictType,
    Permission,
    Role,
    User,
    UserStatus,
)
from app.seeds.definitions import (
    DEPARTMENTS,
    PERMISSIONS,
    ROLES,
    SUPER_ADMIN,
    TEST_USER_PASSWORD,
    TEST_USERS,
)

logger = logging.getLogger(__name__)

DICTIONARY_FILE = Path(__file__).with_name("data_dictionary.json")


async def seed_permissions(session: AsyncSession) -> dict[str, Permission]:
    existing = {p.code: p for p in (await session.scalars(select(Permission))).all()}
    for code, name, module, sort_order in PERMISSIONS:
        if code in existing:
            continue
        perm = Permission(code=code, name=name, module=module, sort_order=sort_order)
        session.add(perm)
        existing[code] = perm
    await session.flush()
    return existing


async def seed_roles(session: AsyncSession, permissions: dict[str, Permission]) -> dict[str, Role]:
    existing = {r.code: r for r in (await session.scalars(select(Role))).all()}
    for code, name, description, data_scope, perm_codes, sort_order in ROLES:
        if code in existing:
            continue
        role = Role(
            code=code,
            name=name,
            description=description,
            data_scope=data_scope,
            is_builtin=True,
            sort_order=sort_order,
        )
        role.permissions = [permissions[c] for c in perm_codes]
        session.add(role)
        existing[code] = role
    await session.flush()
    return existing


async def seed_departments(session: AsyncSession) -> dict[str, Department]:
    existing = {d.code: d for d in (await session.scalars(select(Department))).all()}
    created: list[tuple[Department, str | None]] = []
    for code, name, kind, sort_order, leader, function, parent_code in DEPARTMENTS:
        if code in existing:
            continue
        current = Department(
            code=code,
            name=name,
            kind=kind,
            sort_order=sort_order,
            leader=leader,
            remark=function,
            is_active=True,
        )
        session.add(current)
        existing[code] = current
        created.append((current, parent_code))
    await session.flush()
    id_by_code = {item.code: item.id for item in existing.values()}
    for dept, parent_code in created:
        dept.parent_id = id_by_code[parent_code] if parent_code else None
    await session.flush()
    return existing


def load_dictionary_file() -> list[dict[str, Any]]:
    payload = json.loads(DICTIONARY_FILE.read_text(encoding="utf-8"))
    types: list[dict[str, Any]] = payload["types"]
    return types


async def seed_dictionaries(session: AsyncSession) -> tuple[int, int]:
    types = load_dictionary_file()
    existing_types = {t.code: t for t in (await session.scalars(select(DictType))).all()}
    item_count = 0
    for index, entry in enumerate(types):
        dict_type = existing_types.get(entry["code"])
        if dict_type is None:
            dict_type = DictType(code=entry["code"], name=entry["name"])
            session.add(dict_type)
            existing_types[entry["code"]] = dict_type
        created_type = dict_type.id is None
        if created_type:
            dict_type.ref_standard = entry.get("ref_standard")
            dict_type.applies_to = entry.get("applies_to")
            dict_type.remark = entry.get("remark")
            dict_type.sort_order = index
        await session.flush()

        current_items = {
            item.label
            for item in (
                await session.scalars(select(DictItem).where(DictItem.type_id == dict_type.id))
            ).all()
        }
        for order, raw in enumerate(entry["items"]):
            item_count += 1
            if raw["label"] in current_items:
                continue
            session.add(
                DictItem(
                    type_id=dict_type.id,
                    label=raw["label"],
                    value=raw.get("value"),
                    remark=raw.get("remark"),
                    sort_order=order,
                )
            )
    await session.flush()
    return len(types), item_count


async def seed_test_users(
    session: AsyncSession, roles: dict[str, Role], departments: dict[str, Department]
) -> int:
    created = 0
    for account, name, role_code, department_code, post, is_superuser in TEST_USERS:
        if account == SUPER_ADMIN[0]:
            continue
        user = await session.scalar(select(User).where(User.account == account))
        if user is not None:
            continue
        user = User(
            account=account,
            name=name,
            post=post,
            password_hash=hash_password(TEST_USER_PASSWORD),
            status=UserStatus.ACTIVE,
            is_superuser=is_superuser,
        )
        user.department = departments.get(department_code) if department_code else None
        user.roles = [roles[role_code]]
        session.add(user)
        created += 1
        logger.info("已创建账号 %s（%s），初始密码 %s", account, name, TEST_USER_PASSWORD)

    account, name, role_code, department_code, post = SUPER_ADMIN
    superuser = await session.scalar(select(User).where(User.account == account))
    if superuser is None:
        superuser = User(
            account=account,
            name=name,
            post=post,
            password_hash=hash_password(settings.initial_admin_password),
            status=UserStatus.ACTIVE,
            is_superuser=True,
        )
        superuser.department = departments.get(department_code) if department_code else None
        superuser.roles = [roles[role_code]]
        session.add(superuser)
        created += 1
        logger.info("已创建超级管理员 %s，初始密码来自 INITIAL_ADMIN_PASSWORD", account)
    await session.flush()
    return created


async def seed_all(session: AsyncSession) -> dict[str, int]:
    permissions = await seed_permissions(session)
    roles = await seed_roles(session, permissions)
    departments = await seed_departments(session)
    type_count, item_count = await seed_dictionaries(session)
    await seed_test_users(session, roles, departments)
    await session.commit()
    return {
        "permissions": len(permissions),
        "roles": len(roles),
        "departments": len(departments),
        "dict_types": type_count,
        "dict_items": item_count,
    }


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    async with async_session_factory() as session:
        summary = await seed_all(session)
    logger.info(
        "初始化完成：权限 %(permissions)s，角色 %(roles)s，部门 %(departments)s，"
        "字典 %(dict_types)s 类 / %(dict_items)s 项",
        summary,
    )


if __name__ == "__main__":
    asyncio.run(main())
