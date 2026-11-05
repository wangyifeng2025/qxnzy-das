from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.datasets.spec import DatasetSpec, FieldSpec
from app.models.common import data_collection_timestamp
from app.models.records import BizRecord
from app.models.staff import StaffMember
from app.models.system import User
from app.services.staff import apply_rules
from app.services.staff_rules import TITLE_RANKS, StaffWrite


def _field(
    code: str,
    label: str,
    kind: str,
    group: str,
    *,
    required: bool = False,
    max_length: int | None = None,
    dict_code: str | None = None,
    visible_when: str | None = None,
    sensitive: bool = False,
    default: str | None = None,
) -> FieldSpec:
    return FieldSpec(
        code=code,
        label=label,
        kind=kind,
        group=group,
        required=required,
        max_length=max_length,
        dict_code=dict_code,
        visible_when=visible_when,
        sensitive=sensitive,
        default=default,
    )


def _validate(
    payload: dict[str, object], options: dict[str, set[str]], departments: set[str]
) -> tuple[dict[str, object], list[str]]:
    return apply_rules(StaffWrite.model_validate(payload), options, departments)


async def publish_staff(
    session: AsyncSession, record: BizRecord, data: dict[str, object], user: User
) -> str:
    staff_no = str(data["JGH"])
    id_card = str(data["SFZJH"])
    conflict = await session.scalar(
        select(StaffMember).where(
            or_(StaffMember.JGH == staff_no, StaffMember.SFZJH == id_card),
            StaffMember.ZJSJWYXBS != (record.ods_id or ""),
        )
    )
    if conflict is not None:
        detail = "教工号重复" if conflict.JGH == staff_no else "身份证号重复"
        raise HTTPException(status.HTTP_409_CONFLICT, detail=detail)
    row = None
    if record.ods_id:
        row = await session.get(StaffMember, record.ods_id)
    if row is None:
        row = StaffMember(XXDM=settings.school_code)
        session.add(row)
    for key, value in data.items():
        if key == "CZHYQYGZNX" and value is not None:
            value = Decimal(str(value))
        if key in {"ZYDTNX", "ZYQFZRNX"} and value is not None:
            value = int(str(value))
        setattr(row, key, value)
    row.SJCJSJ = data_collection_timestamp()
    row.TBR = user.name[:36]
    await session.flush()
    return row.ZJSJWYXBS


def staff_dataset() -> DatasetSpec:
    identity = "身份信息"
    education = "学历与学位"
    post = "岗位"
    cert = "高校教师资格证书"
    title = "专业技术职务"
    vocational = "职业资格证书"
    teaching = "教学身份"
    politics = "思政、辅导员与心理健康"
    leader = "带头人与企业经历"
    return DatasetSpec(
        code="ODS_JZGJBSJ",
        name="教职工基本信息",
        category="teacher",
        review_department="BM11",
        business_key_fields=("JGH",),
        owner_field="JGH",
        owner_name_field="JSXM",
        department_field="YXBMCMC",
        list_fields=("JGH", "JSXM", "YXBMCMC", "RYLB", "XL"),
        groups=(
            (identity, "姓名、性别、出生日期须与身份证一致。"),
            (education, None),
            (post, None),
            (cert, "选择“是”后须填写发证单位和获取年月。"),
            (title, "没有职务可留空；填写其中一项时，四项都要填。"),
            (vocational, "没有证书选“无”。"),
            (teaching, None),
            (politics, None),
            (leader, "不是带头人或负责人时，年限为 0。企业工作年限保留 1 位小数。"),
        ),
        fields=(
            _field("JGH", "教工号", "text", identity, required=True, max_length=20),
            _field("JSXM", "姓名", "text", identity, required=True, max_length=36),
            _field("XB", "性别", "select", identity, required=True, dict_code="D55"),
            _field(
                "SFZJH",
                "身份证号",
                "text",
                identity,
                required=True,
                max_length=18,
                sensitive=True,
            ),
            _field("CSRQ", "出生日期", "date", identity, required=True),
            _field("ZZMM", "政治面貌", "select", identity, required=True, dict_code="D21"),
            _field("MZ", "民族", "select", identity, required=True, dict_code="D22"),
            _field("XL", "学历", "select", education, required=True, dict_code="D23"),
            _field("XW", "学位", "select", education, required=True, dict_code="D24"),
            _field(
                "BYXXGJDQ",
                "最高学历毕业学校所在国家（地区）",
                "select",
                education,
                required=True,
                dict_code="D63",
            ),
            _field(
                "BYXXMC",
                "最高学历毕业学校名称",
                "text",
                education,
                required=True,
                max_length=100,
            ),
            _field("YXBMCMC", "院系部名称", "select", post, required=True, dict_code="departments"),
            _field("RYLB", "人员类别", "select", post, required=True, dict_code="D19"),
            _field("SRZW", "所任职务", "text", post, required=True, max_length=60),
            _field("ZYLY", "专业领域", "select", post, required=True, dict_code="D25"),
            _field("ZYTC", "专业特长", "text", post, required=True, max_length=100),
            _field(
                "SFYGXJSZGZS",
                "是否拥有高校教师资格证书",
                "select",
                cert,
                required=True,
                dict_code="D28",
                default="0",
            ),
            _field(
                "GXJSZGZFZDW",
                "发证单位",
                "text",
                cert,
                max_length=60,
                visible_when="SFYGXJSZGZS",
            ),
            _field("GXJSZGZHQRQ", "获取日期", "month", cert, visible_when="SFYGXJSZGZS"),
            _field("ZYJSZWDJ", "专业技术职务等级", "select", title, dict_code="titles"),
            _field("ZYJSZWMC", "专业技术职务名称", "text", title, max_length=60),
            _field("ZYJSZWFZDW", "发证单位", "text", title, max_length=60),
            _field("ZYJSZWHQRQ", "获取日期", "month", title),
            _field("ZYGGZSDJ", "职业资格证书等级", "select", vocational, dict_code="D27"),
            _field("ZYGGZSMC", "职业资格证书名称", "text", vocational, max_length=100),
            _field("ZYGGZSFZDW", "发证单位", "text", vocational, max_length=60),
            _field("ZYGGZSHQRQ", "获取日期", "month", vocational),
            _field(
                "SFZYJS",
                "是否专业教师",
                "select",
                teaching,
                required=True,
                dict_code="D28",
                default="0",
            ),
            _field(
                "XZSSZYMC",
                "行政所属专业名称",
                "text",
                teaching,
                max_length=60,
                visible_when="SFZYJS",
            ),
            _field(
                "XZSSZYDM",
                "行政所属专业代码",
                "text",
                teaching,
                max_length=6,
                visible_when="SFZYJS",
            ),
            _field(
                "XZSSZYCC",
                "行政所属专业层次",
                "select",
                teaching,
                dict_code="D01",
                visible_when="SFZYJS",
            ),
            _field(
                "XZSSZYDL",
                "行政所属专业大类",
                "text",
                teaching,
                max_length=40,
                visible_when="SFZYJS",
            ),
            _field(
                "SFGGKJS",
                "是否公共课教师",
                "select",
                teaching,
                required=True,
                dict_code="D28",
                default="0",
            ),
            _field(
                "SRGGKC",
                "所任公共课程",
                "select",
                teaching,
                dict_code="D14",
                visible_when="SFGGKJS",
            ),
            _field(
                "SFSZXJS",
                "是否为双师型教师",
                "select",
                teaching,
                required=True,
                dict_code="D29",
                default="否",
            ),
            _field(
                "JXMS",
                "教学名师",
                "select",
                teaching,
                required=True,
                dict_code="D30",
                default="否",
            ),
            _field(
                "SFZZSZKJS",
                "是否专职思政课教师",
                "select",
                politics,
                required=True,
                dict_code="D28",
                default="0",
            ),
            _field(
                "SFJZSZKJS",
                "是否兼职思政课教师",
                "select",
                politics,
                required=True,
                dict_code="D28",
                default="0",
            ),
            _field(
                "SFZZFDY",
                "是否专职辅导员",
                "select",
                politics,
                required=True,
                dict_code="D28",
                default="0",
            ),
            _field(
                "SFJZFDY",
                "是否兼职辅导员",
                "select",
                politics,
                required=True,
                dict_code="D28",
                default="0",
            ),
            _field(
                "SFZZXLJKJS",
                "是否专职心理健康教师",
                "select",
                politics,
                required=True,
                dict_code="D28",
                default="0",
            ),
            _field(
                "SFJZXLJKJS",
                "是否兼职心理健康教师",
                "select",
                politics,
                required=True,
                dict_code="D28",
                default="0",
            ),
            _field(
                "SFZYDTR",
                "是否专业带头人",
                "select",
                leader,
                required=True,
                dict_code="D31",
                default="否",
            ),
            _field("ZYDTNX", "担任专业带头人年限", "number", leader, required=True, default="0"),
            _field(
                "SFZYQFZR",
                "是否专业（群）负责人",
                "select",
                leader,
                required=True,
                dict_code="D32",
                default="否",
            ),
            _field(
                "ZYQFZRNX",
                "担任专业（群）负责人年限",
                "number",
                leader,
                required=True,
                default="0",
            ),
            _field(
                "CZHYQYGZNX",
                "曾在行业企业工作年限",
                "decimal",
                leader,
                required=True,
                default="0.0",
            ),
        ),
        validate=_validate,
        publish=publish_staff,
    )


AWARD_REVIEW = "owner_department"
TITLE_RANK_OPTIONS = TITLE_RANKS
