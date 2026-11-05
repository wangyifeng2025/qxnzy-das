from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import Department, DepartmentKind, DictItem, Role, User
from app.seeds.initial_data import seed_all


async def test_seed_does_not_overwrite_existing_records(db_session: AsyncSession) -> None:
    user = await db_session.scalar(select(User).where(User.account == "2024020008"))
    role = await db_session.scalar(select(Role).where(Role.code == "teacher"))
    department = await db_session.scalar(select(Department).where(Department.code == "BM04"))
    item = await db_session.scalar(select(DictItem).limit(1))
    assert user is not None and role is not None and department is not None and item is not None

    user.post = "界面上的岗位"
    role.name = "界面上的教师"
    department.leader = "界面上的负责人"
    item.remark = "界面上的备注"
    db_session.add(
        Department(code="BM99", name="界面新增部门", kind=DepartmentKind.OTHER, sort_order=99)
    )
    await db_session.commit()

    await seed_all(db_session)

    assert user.post == "界面上的岗位"
    assert role.name == "界面上的教师"
    assert department.leader == "界面上的负责人"
    assert item.remark == "界面上的备注"
    kept = await db_session.scalar(select(Department).where(Department.code == "BM99"))
    assert kept is not None


async def test_seed_inserts_missing_user(db_session: AsyncSession) -> None:
    user = await db_session.scalar(select(User).where(User.account == "kyc01"))
    assert user is not None
    await db_session.delete(user)
    await db_session.commit()

    await seed_all(db_session)

    restored = await db_session.scalar(select(User).where(User.account == "kyc01"))
    assert restored is not None
    assert restored.department is not None
    assert restored.department.code == "BM22"
