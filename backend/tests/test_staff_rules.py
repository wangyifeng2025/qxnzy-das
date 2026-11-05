from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.system import DataScope, Department, Permission, Role, User
from app.services.staff import assert_scope, can_submit
from app.services.staff_rules import StaffWrite, id_card_birth_gender, normalize_staff

_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_CHECKS = "10X98765432"


def valid_id(birth: str = "19900307", order: str = "013") -> str:
    body = f"520102{birth}{order}"
    total = sum(int(body[index]) * _WEIGHTS[index] for index in range(17))
    return body + _CHECKS[total % 11]


def options() -> dict[str, set[str]]:
    allowed = {
        "1",
        "2",
        "0",
        "是",
        "否",
        "无",
        "群众",
        "汉族",
        "本科",
        "中国",
        "学士",
        "专任教师",
        "其他",
    }
    codes = (
        "D01",
        "D14",
        "D19",
        "D21",
        "D22",
        "D23",
        "D24",
        "D25",
        "D27",
        "D28",
        "D29",
        "D30",
        "D31",
        "D32",
        "D55",
        "D63",
    )
    return {code: set(allowed) for code in codes}


def payload(**overrides: object) -> StaffWrite:
    identity = valid_id()
    birth, gender, errors = id_card_birth_gender(identity)
    assert errors == []
    data: dict[str, object] = {
        "YXBMCMC": "机械与电子工程系",
        "JGH": "2024020008",
        "JSXM": "谭元霸",
        "XB": gender,
        "SFZJH": identity,
        "CSRQ": birth,
        "ZZMM": "群众",
        "MZ": "汉族",
        "XL": "本科",
        "BYXXGJDQ": "中国",
        "BYXXMC": "贵州大学",
        "XW": "学士",
        "RYLB": "专任教师",
        "SRZW": "教师",
        "ZYLY": "其他",
        "ZYTC": "软件",
        "SFYGXJSZGZS": "0",
        "SFZYJS": "0",
        "SFGGKJS": "0",
        "SFSZXJS": "否",
        "JXMS": "否",
        "SFZZSZKJS": "0",
        "SFJZSZKJS": "0",
        "SFZZFDY": "0",
        "SFJZFDY": "0",
        "SFZZXLJKJS": "0",
        "SFJZXLJKJS": "0",
        "SFZYDTR": "否",
        "SFZYQFZR": "否",
        "CZHYQYGZNX": Decimal("1.0"),
    }
    data.update(overrides)
    return StaffWrite.model_validate(data)


def test_valid_staff_has_no_errors() -> None:
    _data, errors, warnings = normalize_staff(payload(), options(), {"机械与电子工程系"})
    assert errors == []
    assert warnings == []


def test_id_checksum_and_gender_mismatch() -> None:
    _data, errors, _warnings = normalize_staff(
        payload(SFZJH="520102199003070130", XB="1", CSRQ="1990-03-07"),
        options(),
        {"机械与电子工程系"},
    )
    assert "身份证号格式或校验位错误" in errors

    identity = valid_id()
    _data, errors, _warnings = normalize_staff(
        payload(SFZJH=identity, XB="2"),
        options(),
        {"机械与电子工程系"},
    )
    assert "性别与身份证号不一致" in errors


def test_teacher_certificate_requires_issuer() -> None:
    _data, errors, _warnings = normalize_staff(
        payload(SFYGXJSZGZS="1"),
        options(),
        {"机械与电子工程系"},
    )
    assert "有教师资格证须填写发证单位和日期" in errors


def user_with(
    *,
    role_code: str,
    data_scope: str,
    account: str = "2024020008",
    department: Department | None = None,
    permissions: tuple[str, ...] = (),
    is_superuser: bool = False,
) -> User:
    role = Role(code=role_code, name=role_code, data_scope=data_scope)
    role.permissions = [
        Permission(code=code, name=code, module="测试", sort_order=1) for code in permissions
    ]
    user = User(account=account, name="测试", password_hash="x", is_superuser=is_superuser)
    user.roles = [role]
    user.department = department
    return user


def test_teacher_can_only_maintain_self() -> None:
    teacher = user_with(
        role_code="teacher", data_scope=DataScope.SELF, permissions=("fill:submit",)
    )
    assert_scope(teacher, department="机械与电子工程系", staff_no="2024020008")
    with pytest.raises(HTTPException, match="只能维护本人"):
        assert_scope(teacher, department="机械与电子工程系", staff_no="2004020159")


def test_department_scope_and_auditor_domain() -> None:
    department = Department(code="BM04", name="机械与电子工程系")
    staff = user_with(
        role_code="staff",
        data_scope=DataScope.DEPARTMENT,
        department=department,
        permissions=("fill:submit",),
    )
    assert_scope(staff, department="机械与电子工程系", staff_no="2000000001")
    with pytest.raises(HTTPException, match="只能维护本部门"):
        assert_scope(staff, department="医护系", staff_no="2000000001")

    research = user_with(
        role_code="auditor",
        data_scope=DataScope.ALL,
        account="kyc01",
        department=Department(code="BM22", name="科研处"),
        permissions=("fill:submit",),
    )
    assert can_submit(research) is False
    with pytest.raises(HTTPException, match="组织人事部"):
        assert_scope(research, department="机械与电子工程系", staff_no="2024020008")

    personnel = user_with(
        role_code="auditor",
        data_scope=DataScope.ALL,
        account="zzrsb01",
        department=Department(code="BM11", name="组织人事部"),
        permissions=("fill:submit",),
    )
    assert can_submit(personnel) is True
    assert_scope(personnel, department="医护系", staff_no="2000000001")
