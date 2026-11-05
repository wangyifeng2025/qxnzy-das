from fastapi import HTTPException, status
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.common import data_collection_timestamp
from app.models.staff import StaffMember
from app.models.system import DataScope, Department, DictItem, DictType, User
from app.schemas.staff import DictOption, StaffFormMeta, StaffListItem, StaffMemberRead
from app.services.staff_rules import TITLE_RANKS, StaffWrite, normalize_staff

DICT_CODES = (
    "D01",
    "D02",
    "D03",
    "D04",
    "D05",
    "D06",
    "D07",
    "D08",
    "D09",
    "D11",
    "D12",
    "D13",
    "D14",
    "D15",
    "D16",
    "D18",
    "D19",
    "D20",
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
    "D33",
    "D34",
    "D35",
    "D36",
    "D37",
    "D38",
    "D39",
    "D40",
    "D41",
    "D42",
    "D43",
    "D44",
    "D45",
    "D46",
    "D47",
    "D48",
    "D49",
    "D50",
    "D51",
    "D52",
    "D53",
    "D54",
    "D55",
    "D56",
    "D57",
    "D59",
    "D61",
    "D62",
    "D63",
    "D64",
    "D65",
    "D66",
    "D67",
    "D68",
    "D69",
)


def mask_id_card(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


STAFF_REVIEW_DEPARTMENT_CODE = "BM11"


def outside_staff_domain(user: User) -> bool:
    """业务部门审核员只能处理本部门负责的数据域；教职工基本信息归组织人事部。"""
    if user.is_superuser:
        return False
    codes = {role.code for role in user.roles}
    if "auditor" not in codes or "admin" in codes:
        return False
    return user.department is None or user.department.code != STAFF_REVIEW_DEPARTMENT_CODE


def can_submit(user: User) -> bool:
    if outside_staff_domain(user):
        return False
    return user.is_superuser or "fill:submit" in user.permission_codes


def stored_option(item: DictItem) -> str:
    return item.value if item.value else item.label


async def load_dict_options(
    session: AsyncSession,
) -> tuple[dict[str, list[DictOption]], dict[str, set[str]]]:
    rows = (
        await session.scalars(
            select(DictType).where(DictType.code.in_(DICT_CODES), DictType.is_active.is_(True))
        )
    ).all()
    # items are lazy by default; load explicitly to stay async-safe
    found: dict[str, list[DictOption]] = {}
    for dict_type in rows:
        items = (
            await session.scalars(
                select(DictItem)
                .where(DictItem.type_id == dict_type.id, DictItem.is_active.is_(True))
                .order_by(DictItem.sort_order, DictItem.id)
            )
        ).all()
        found[dict_type.code] = [
            DictOption(value=stored_option(item), label=item.label) for item in items
        ]
    missing = [code for code in DICT_CODES if code not in found or not found[code]]
    if missing:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"数据字典未初始化：{'、'.join(missing)}",
        )
    allowed = {code: {option.value for option in options} for code, options in found.items()}
    return found, allowed


async def active_department_names(session: AsyncSession) -> set[str]:
    names = await session.scalars(
        select(Department.name)
        .where(Department.is_active.is_(True))
        .order_by(Department.sort_order)
    )
    return set(names.all())


def allowed_departments(user: User, names: set[str]) -> list[str]:
    if outside_staff_domain(user):
        return []
    if user.is_superuser or user.data_scope == DataScope.ALL:
        return sorted(names)
    if user.department is not None and user.department.name in names:
        return [user.department.name]
    if user.data_scope == DataScope.DEPARTMENT:
        return []
    return sorted(names)


def assert_scope(user: User, *, department: str, staff_no: str) -> None:
    if outside_staff_domain(user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="教职工基本信息由组织人事部审核与维护"
        )
    if user.is_superuser or user.data_scope == DataScope.ALL:
        return
    if user.data_scope == DataScope.DEPARTMENT:
        if user.department is None or department != user.department.name:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="只能维护本部门教职工")
        return
    if staff_no != user.account:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="只能维护本人的教职工基本信息")
    if user.department is not None and department != user.department.name:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="院系部名称须与当前账号所属部门一致")


def apply_rules(
    payload: StaffWrite, options: dict[str, set[str]], departments: set[str]
) -> tuple[dict[str, object], list[str]]:
    data, errors, warnings = normalize_staff(payload, options, departments)
    if errors:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="；".join(errors))
    return data, warnings


def to_read(row: StaffMember, warnings: list[str] | None = None) -> StaffMemberRead:
    read = StaffMemberRead.model_validate(row)
    read.warnings = warnings or []
    return read


def to_list_item(row: StaffMember) -> StaffListItem:
    return StaffListItem(
        ZJSJWYXBS=row.ZJSJWYXBS,
        JGH=row.JGH,
        JSXM=row.JSXM,
        XB=row.XB,
        YXBMCMC=row.YXBMCMC,
        RYLB=row.RYLB,
        XL=row.XL,
        SFZJH=mask_id_card(row.SFZJH),
        SJCJSJ=row.SJCJSJ,
    )


async def ensure_unique(
    session: AsyncSession, staff_no: str, id_card: str, exclude_id: str | None
) -> None:
    query = select(StaffMember).where(
        or_(StaffMember.JGH == staff_no, StaffMember.SFZJH == id_card)
    )
    if exclude_id is not None:
        query = query.where(StaffMember.ZJSJWYXBS != exclude_id)
    existing = await session.scalar(query)
    if existing is None:
        return
    if existing.JGH == staff_no:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="教工号重复")
    raise HTTPException(status.HTTP_409_CONFLICT, detail="身份证号重复")


def assign_row(row: StaffMember, data: dict[str, object], user: User) -> None:
    for key, value in data.items():
        setattr(row, key, value)
    row.SJCJSJ = data_collection_timestamp()
    row.TBR = user.name[:36]


def scoped_query(user: User) -> Select[tuple[StaffMember]]:
    query = select(StaffMember)
    if outside_staff_domain(user):
        return query.where(StaffMember.ZJSJWYXBS == "")
    if user.is_superuser or user.data_scope == DataScope.ALL:
        return query
    if user.data_scope == DataScope.DEPARTMENT:
        if user.department is None:
            return query.where(StaffMember.ZJSJWYXBS == "")
        return query.where(StaffMember.YXBMCMC == user.department.name)
    return query.where(StaffMember.JGH == user.account)


def form_meta(
    user: User,
    departments: list[str],
    dicts: dict[str, list[DictOption]],
) -> StaffFormMeta:
    return StaffFormMeta(
        departments=departments,
        dicts=dicts,
        title_ranks=list(TITLE_RANKS),
        scope=DataScope.ALL if user.is_superuser else user.data_scope,
        account=user.account,
        name=user.name,
        department_name=user.department.name if user.department is not None else None,
        can_submit=can_submit(user),
    )
