"""教师类数据集：培训、获奖、论文、实践、纵向、横向、知识产权。

业务主键与 ODS 表唯一约束一致，发布时按同一组字段查重。
获奖信息的业务审核部门是所属系部，没有职能部门环节。
"""

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.datasets.access import OWNER_DEPARTMENT
from app.datasets.spec import DatasetSpec, FieldSpec, Publish
from app.datasets.validate import Hook, check_fields
from app.models.base import Base
from app.models.common import data_collection_timestamp
from app.models.records import BizRecord
from app.models.research import HorizontalResearchProject, IntellectualProperty, ResearchProject
from app.models.system import User
from app.models.teacher_activity import (
    EnterprisePractice,
    TeacherAward,
    TeacherPublication,
    TeacherTraining,
)

PERSON = "人员与部门"
_Model = type[Base]


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
        default=default,
    )


def _person(owner: str, owner_label: str, name: str, name_label: str) -> tuple[FieldSpec, ...]:
    return (
        _field(owner, owner_label, "text", PERSON, required=True, max_length=20),
        _field(name, name_label, "text", PERSON, required=True, max_length=36),
        _field("JSLB", "教师类别", "select", PERSON, required=True, dict_code="D20"),
        _field(
            "YXBMCMC",
            "院系部名称",
            "select",
            PERSON,
            required=True,
            dict_code="departments",
            max_length=60,
        ),
    )


def _flag(code: str, label: str, group: str) -> FieldSpec:
    return _field(code, label, "select", group, required=True, dict_code="D28", default="0")


def _company(group: str, parent: str) -> FieldSpec:
    return _field(
        "HZQYMC",
        "合作企业名称",
        "text",
        group,
        required=True,
        max_length=200,
        visible_when=parent,
    )


def _positive(code: str, label: str) -> Hook:
    def hook(data: dict[str, object], errors: list[str]) -> None:
        value = data.get(code)
        if isinstance(value, int) and value <= 0:
            errors.append(f"{label}须大于 0")

    return hook


def _not_before(later: str, earlier: str, message: str) -> Hook:
    def hook(data: dict[str, object], errors: list[str]) -> None:
        end = data.get(later)
        start = data.get(earlier)
        if isinstance(end, str) and isinstance(start, str) and end < start:
            errors.append(message)

    return hook


def _chain(*hooks: Hook) -> Hook:
    def hook(data: dict[str, object], errors: list[str]) -> None:
        for item in hooks:
            item(data, errors)

    return hook


def _horizontal_amounts(data: dict[str, object], errors: list[str]) -> None:
    year = data.get("BXNDKJE")
    total = data.get("LJDKJE")
    if isinstance(year, Decimal) and isinstance(total, Decimal) and total < year:
        errors.append("累计到账金额不能小于本学年到账金额")


def _transfer(data: dict[str, object], errors: list[str]) -> None:
    amount = data.get("ZRXKJE")
    missing = not data.get("SRFMC") or not data.get("ZRXKRQ")
    if isinstance(amount, Decimal) and amount > 0 and missing:
        errors.append("转让或许可金额大于 0 时须填写受让方和日期")


def _publisher(model: _Model, unique: tuple[str, ...]) -> Publish:
    async def publish(
        session: AsyncSession, record: BizRecord, data: dict[str, object], user: User
    ) -> str:
        converted = _typed(data)
        clauses = [getattr(model, name) == converted[name] for name in unique]
        query = select(model).where(*clauses)
        if record.ods_id:
            query = query.where(model.ZJSJWYXBS != record.ods_id)  # type: ignore[attr-defined]
        if await session.scalar(query) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="已发布数据中存在相同业务主键")
        row = await session.get(model, record.ods_id) if record.ods_id else None
        if row is None:
            row = model()
            row.XXDM = settings.school_code  # type: ignore[attr-defined]
            session.add(row)
        for key, value in converted.items():
            setattr(row, key, value)
        row.SJCJSJ = data_collection_timestamp()  # type: ignore[attr-defined]
        row.TBR = user.name[:36]  # type: ignore[attr-defined]
        await session.flush()
        identifier = row.ZJSJWYXBS  # type: ignore[attr-defined]
        if not isinstance(identifier, str):
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="发布失败")
        return identifier

    return publish


def _typed(data: dict[str, object]) -> dict[str, object]:
    converted: dict[str, object] = {}
    for key, value in data.items():
        if key in {"PXTS", "SJTS", "CYJSS"} and value is not None:
            converted[key] = int(str(value))
        elif key in {"LXJF", "LJDKJE", "BXNDKJE", "ZRXKJE"} and value is not None:
            converted[key] = Decimal(str(value))
        else:
            converted[key] = value
    return converted


def _spec(
    *,
    code: str,
    name: str,
    review_department: str,
    business_key_fields: tuple[str, ...],
    owner_field: str,
    owner_name_field: str,
    list_fields: tuple[str, ...],
    groups: tuple[tuple[str, str | None], ...],
    fields: tuple[FieldSpec, ...],
    model: _Model,
    hook: Hook | None = None,
) -> DatasetSpec:
    def validate(
        payload: dict[str, object], options: dict[str, set[str]], departments: set[str]
    ) -> tuple[dict[str, object], list[str]]:
        return check_fields(fields, payload, options, departments, hook)

    return DatasetSpec(
        code=code,
        name=name,
        category="teacher",
        review_department=review_department,
        business_key_fields=business_key_fields,
        owner_field=owner_field,
        owner_name_field=owner_name_field,
        department_field="YXBMCMC",
        list_fields=list_fields,
        fields=fields,
        groups=groups,
        validate=validate,
        publish=_publisher(model, business_key_fields),
    )


def teacher_datasets() -> tuple[DatasetSpec, ...]:
    return (
        _training(),
        _award(),
        _publication(),
        _practice(),
        _vertical(),
        _horizontal(),
        _intellectual_property(),
    )


def _training() -> DatasetSpec:
    group = "培训交流"
    fields = (
        *_person("JGH", "教工号", "JSXM", "教师姓名"),
        _field("JXPXMC", "项目名称", "text", group, required=True, max_length=200),
        _field("JXPXLX", "培训交流类型", "select", group, required=True, dict_code="D33"),
        _field("JXPXFS", "培训形式", "select", group, required=True, dict_code="D34"),
        _field("JBBMMC", "举办部门名称", "text", group, required=True, max_length=100),
        _field("JXPXJB", "培训交流级别", "select", group, required=True, dict_code="D35"),
        _field("PXTS", "时长（天）", "number", group, required=True, default="1"),
        _field("JXPXDD", "培训交流地点", "text", group, required=True, max_length=100),
        _field("PCBMMC", "派出部门名称", "text", group, required=True, max_length=60),
        _field("PCBMJB", "派出部门级别", "select", group, required=True, dict_code="D36"),
    )
    return _spec(
        code="ODS_XXJXSJ",
        name="教师培训与交流",
        review_department="BM11",
        business_key_fields=("JGH", "JXPXMC", "JXPXLX", "JXPXDD"),
        owner_field="JGH",
        owner_name_field="JSXM",
        list_fields=("JGH", "JSXM", "JXPXMC", "JXPXLX", "YXBMCMC"),
        groups=(
            (PERSON, None),
            (group, "时长按天填写，须大于 0。"),
        ),
        fields=fields,
        model=TeacherTraining,
        hook=_positive("PXTS", "时长（天）"),
    )


def _award() -> DatasetSpec:
    group = "奖项"
    fields = (
        *_person("DYHJRGH", "第一获奖人工号", "DYHJRXM", "第一获奖人姓名"),
        _field("HJMC", "获奖名称", "text", group, required=True, max_length=200),
        _field("JB", "级别", "select", group, required=True, dict_code="D37"),
        _field("DJ", "等级", "select", group, required=True, dict_code="D38"),
        _field("HJLB", "奖项类别", "select", group, required=True, dict_code="D39"),
        _flag("SFXQHZ", "是否校企合作", group),
        _company(group, "SFXQHZ"),
        _field("BJDWMC", "颁奖单位名称", "text", group, required=True, max_length=100),
        _field("HJRQ", "获奖日期", "month", group, required=True),
        _field("HJRSC", "获奖人顺序", "select", group, required=True, dict_code="D40"),
        _flag("SFDYWCDW", "学校是否第一完成单位", group),
    )
    return _spec(
        code="ODS_JSHJSJ",
        name="教师获奖信息",
        review_department=OWNER_DEPARTMENT,
        business_key_fields=("DYHJRGH", "HJMC", "HJRQ"),
        owner_field="DYHJRGH",
        owner_name_field="DYHJRXM",
        list_fields=("DYHJRGH", "DYHJRXM", "HJMC", "HJRQ", "YXBMCMC"),
        groups=((PERSON, None), (group, "选择校企合作后须填写合作企业。")),
        fields=fields,
        model=TeacherAward,
    )


def _publication() -> DatasetSpec:
    group = "成果"
    fields = (
        *_person("DYZGH", "第一作者工号", "DYZXM", "第一作者姓名"),
        _field("ZZMC", "著作名称", "text", group, required=True, max_length=200),
        _field("CGSX", "成果形式", "select", group, required=True, dict_code="D41"),
        _field("LWFL", "著作与论文分类", "select", group, required=True, dict_code="D42"),
        _field("CBSMC", "出版社或杂志社", "text", group, required=True, max_length=180),
        _field("FBRQ", "出版或发表日期", "month", group, required=True),
        _field("WCDWSC", "完成单位顺序", "select", group, required=True, dict_code="D43"),
    )
    return _spec(
        code="ODS_LWZZSJ",
        name="教师论文著作",
        review_department="BM22",
        business_key_fields=("DYZGH", "ZZMC", "FBRQ"),
        owner_field="DYZGH",
        owner_name_field="DYZXM",
        list_fields=("DYZGH", "DYZXM", "ZZMC", "FBRQ", "YXBMCMC"),
        groups=((PERSON, None), (group, None)),
        fields=fields,
        model=TeacherPublication,
    )


def _practice() -> DatasetSpec:
    group = "实践单位"
    fields = (
        *_person("JGH", "教工号", "JSXM", "教师姓名"),
        _field("QYDLLX", "类型", "select", group, required=True, dict_code="D52"),
        _field("JSDWMC", "接收单位名称", "text", group, required=True, max_length=100),
        _field("GWMC", "岗位名称", "text", group, required=True, max_length=60),
        _field("SJTS", "时长（天）", "number", group, required=True, default="1"),
        _field("JSDDSZD", "接收单位所在地", "select", group, required=True, dict_code="D53"),
        _field("PCBMMC", "派出（推荐）部门名称", "text", group, required=True, max_length=60),
        _field("PCBMJB", "派出（推荐）部门级别", "select", group, required=True, dict_code="D36"),
    )
    return _spec(
        code="ODS_JSQYJZSJSJ",
        name="教师企业实践锻炼",
        review_department="BM11",
        business_key_fields=("JGH", "QYDLLX", "JSDWMC", "GWMC"),
        owner_field="JGH",
        owner_name_field="JSXM",
        list_fields=("JGH", "JSXM", "JSDWMC", "QYDLLX", "YXBMCMC"),
        groups=((PERSON, None), (group, "时长按天填写，须大于 0。")),
        fields=fields,
        model=EnterprisePractice,
        hook=_positive("SJTS", "时长（天）"),
    )


def _money(code: str, label: str, group: str) -> FieldSpec:
    return _field(code, label, "decimal", group, required=True, default="0")


def _closing(group: str) -> tuple[FieldSpec, ...]:
    return (
        _field("JXRQ", "结项日期", "month", group),
        _field("JDBM", "鉴定部门", "text", group, max_length=100),
        _field("JDJG", "鉴定结果", "select", group, dict_code="D51"),
    )


def _vertical() -> DatasetSpec:
    topic = "课题"
    money = "经费与结项"
    fields = (
        *_person("DYZCRGH", "第一主持人工号", "DYZCRXM", "第一主持人姓名"),
        _field("KTMC", "课题名称", "text", topic, required=True, max_length=300),
        _field("KTFL", "课题分类", "select", topic, required=True, dict_code="D44"),
        _field("KTXZ", "课题性质", "select", topic, required=True, dict_code="D45"),
        _field("YJZT", "研究状态", "select", topic, required=True, dict_code="D46"),
        _field("KTLY", "课题来源", "select", topic, required=True, dict_code="D47"),
        _field("PZBMMC", "批准部门名称", "text", topic, required=True, max_length=100),
        _field("KTJB", "课题级别", "select", topic, required=True, dict_code="D49"),
        _field("LXRQ", "立项日期", "month", topic, required=True),
        _field("JFLY", "经费来源", "select", money, required=True, dict_code="D50"),
        _money("LXJF", "立项经费", money),
        *_closing(money),
        _money("LJDKJE", "累计到款金额", money),
        _flag("SFXQHZWC", "是否校企合作完成", money),
        _company(money, "SFXQHZWC"),
        _field("CYJSS", "参与教师人数", "number", money, required=True, default="1"),
    )
    return _spec(
        code="ODS_KYXMJBSJ",
        name="纵向科研项目",
        review_department="BM22",
        business_key_fields=("DYZCRGH", "KTMC", "LXRQ"),
        owner_field="DYZCRGH",
        owner_name_field="DYZCRXM",
        list_fields=("DYZCRGH", "DYZCRXM", "KTMC", "LXRQ", "YXBMCMC"),
        groups=(
            (PERSON, None),
            (topic, None),
            (money, "结项日期不能早于立项日期。选择校企合作后须填写企业名称。"),
        ),
        fields=fields,
        model=ResearchProject,
        hook=_chain(
            _positive("CYJSS", "参与教师人数"),
            _not_before("JXRQ", "LXRQ", "结项日期不能早于立项日期"),
        ),
    )


def _horizontal() -> DatasetSpec:
    topic = "课题"
    money = "经费与结项"
    fields = (
        *_person("DYZCRGH", "第一主持人工号", "DYZCRXM", "第一主持人姓名"),
        _field("KTMC", "课题名称", "text", topic, required=True, max_length=300),
        _field("YJZT", "研究状态", "select", topic, required=True, dict_code="D46"),
        _field("KTLY", "课题来源", "select", topic, required=True, dict_code="D48"),
        _flag("SFLYXQHZQY", "是否来源校企合作企业", topic),
        _field("WTFMC", "委托方名称", "text", topic, required=True, max_length=100),
        _field("LXRQ", "立项日期", "month", topic, required=True),
        _money("BXNDKJE", "本学年到账金额", money),
        *_closing(money),
        _money("LJDKJE", "累计到账金额", money),
        _flag("SFXQHZWC", "是否校企合作完成", money),
        _company(money, "SFXQHZWC"),
        _field("FWLX", "服务类型", "select", money, required=True, dict_code="D67"),
    )
    return _spec(
        code="ODS_HXKTSJ",
        name="横向课题",
        review_department="BM22",
        business_key_fields=("DYZCRGH", "KTMC", "LXRQ"),
        owner_field="DYZCRGH",
        owner_name_field="DYZCRXM",
        list_fields=("DYZCRGH", "DYZCRXM", "KTMC", "LXRQ", "YXBMCMC"),
        groups=(
            (PERSON, None),
            (topic, None),
            (money, "累计到账金额不能小于本学年到账金额。结项日期不能早于立项日期。"),
        ),
        fields=fields,
        model=HorizontalResearchProject,
        hook=_chain(
            _horizontal_amounts,
            _not_before("JXRQ", "LXRQ", "结项日期不能早于立项日期"),
        ),
    )


def _intellectual_property() -> DatasetSpec:
    group = "知识产权"
    fields = (
        *_person("DYFMRGH", "第一发明人工号", "DYFMRXM", "第一发明人姓名"),
        _field("ZSCQMC", "知识产权项目名称", "text", group, required=True, max_length=200),
        _field("ZSCQBH", "知识产权编号", "text", group, required=True, max_length=32),
        _field("XMLX", "项目类型", "select", group, required=True, dict_code="D54"),
        _field("HDRQ", "获得日期", "month", group, required=True),
        _flag("SFXQHZWC", "是否校企合作完成", group),
        _company(group, "SFXQHZWC"),
        _money("ZRXKJE", "转让/许可金额", group),
        _field("SRFMC", "受让方名称", "text", group, max_length=100),
        _field("ZRXKRQ", "转让/许可日期", "month", group),
    )
    return _spec(
        code="ODS_ZSCQSJ",
        name="教师知识产权",
        review_department="BM22",
        business_key_fields=("ZSCQBH",),
        owner_field="DYFMRGH",
        owner_name_field="DYFMRXM",
        list_fields=("DYFMRGH", "DYFMRXM", "ZSCQMC", "ZSCQBH", "YXBMCMC"),
        groups=(
            (PERSON, None),
            (group, "转让或许可金额大于 0 时须填写受让方和日期。"),
        ),
        fields=fields,
        model=IntellectualProperty,
        hook=_transfer,
    )


def award_dataset() -> DatasetSpec:
    return next(item for item in teacher_datasets() if item.code == "ODS_JSHJSJ")
