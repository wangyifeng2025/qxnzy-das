from decimal import Decimal

from sqlalchemy import CheckConstraint, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.common import data_collection_timestamp, uuid_hex


class StaffMember(Base):
    __tablename__ = "ODS_JZGJBSJ"
    ZJSJWYXBS: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=uuid_hex, comment="主键数据唯一性标识"
    )
    XXDM: Mapped[str] = mapped_column(String(10), comment="学校代码")

    __table_args__ = (
        UniqueConstraint("JGH", name="uq_ODS_JZGJBSJ_JGH"),
        UniqueConstraint("SFZJH", name="uq_ODS_JZGJBSJ_SFZJH"),
        CheckConstraint(
            '"SFYGXJSZGZS" <> \'1\' OR ("GXJSZGZFZDW" IS NOT NULL AND "GXJSZGZHQRQ" IS NOT NULL)',
            name="ck_ODS_JZGJBSJ_JSZGZS_required",
        ),
        CheckConstraint(
            "\"SFZYJS\" <> '1' OR "
            '("XZSSZYMC" IS NOT NULL AND "XZSSZYDM" IS NOT NULL AND '
            '"XZSSZYCC" IS NOT NULL AND "XZSSZYDL" IS NOT NULL)',
            name="ck_ODS_JZGJBSJ_ZYJS_required",
        ),
        CheckConstraint(
            '"SFGGKJS" <> \'1\' OR "SRGGKC" IS NOT NULL',
            name="ck_ODS_JZGJBSJ_GGKJS_required",
        ),
        CheckConstraint(
            '"ZYDTNX" IS NULL OR "ZYDTNX" >= 0',
            name="ck_ODS_JZGJBSJ_ZYDTNX_nonnegative",
        ),
        CheckConstraint(
            '"ZYQFZRNX" IS NULL OR "ZYQFZRNX" >= 0',
            name="ck_ODS_JZGJBSJ_ZYQFZRNX_nonnegative",
        ),
        CheckConstraint('"CZHYQYGZNX" >= 0', name="ck_ODS_JZGJBSJ_QYNX_nonnegative"),
    )

    YXBMCMC: Mapped[str] = mapped_column(String(60), comment="院系部名称")
    JGH: Mapped[str] = mapped_column(String(20), comment="教工号")
    JSXM: Mapped[str] = mapped_column(String(36), comment="姓名")
    XB: Mapped[str] = mapped_column(String(1), comment="性别")
    SFZJH: Mapped[str] = mapped_column(String(18), comment="身份证号")
    CSRQ: Mapped[str] = mapped_column(String(10), comment="出生日期")
    ZZMM: Mapped[str] = mapped_column(String(20), comment="政治面貌")
    MZ: Mapped[str] = mapped_column(String(20), comment="民族")
    XL: Mapped[str] = mapped_column(String(20), comment="学历")
    BYXXGJDQ: Mapped[str] = mapped_column(String(60), comment="最高学历毕业学校所在国家（地区）")
    BYXXMC: Mapped[str] = mapped_column(String(100), comment="最高学历毕业学校名称")
    XW: Mapped[str] = mapped_column(String(10), comment="学位")
    RYLB: Mapped[str] = mapped_column(String(20), comment="人员类别")
    SRZW: Mapped[str] = mapped_column(String(60), comment="所任职务")
    ZYLY: Mapped[str] = mapped_column(String(20), comment="专业领域")
    ZYTC: Mapped[str] = mapped_column(String(100), comment="专业特长")
    SFYGXJSZGZS: Mapped[str] = mapped_column(String(1), comment="是否拥有高校教师资格证书")
    GXJSZGZFZDW: Mapped[str | None] = mapped_column(String(60), comment="高校教师资格证书发证单位")
    GXJSZGZHQRQ: Mapped[str | None] = mapped_column(String(7), comment="高校教师资格证书获取日期")
    ZYJSZWDJ: Mapped[str | None] = mapped_column(String(20), comment="专业技术职务等级")
    ZYJSZWMC: Mapped[str | None] = mapped_column(String(60), comment="专业技术职务名称")
    ZYJSZWFZDW: Mapped[str | None] = mapped_column(String(60), comment="专业技术职务发证单位")
    ZYJSZWHQRQ: Mapped[str | None] = mapped_column(String(7), comment="专业技术职务获取日期")
    ZYGGZSDJ: Mapped[str | None] = mapped_column(String(10), comment="职业资格证书等级")
    ZYGGZSMC: Mapped[str | None] = mapped_column(String(100), comment="职业资格证书名称")
    ZYGGZSFZDW: Mapped[str | None] = mapped_column(String(60), comment="职业资格证书发证单位")
    ZYGGZSHQRQ: Mapped[str | None] = mapped_column(String(7), comment="职业资格证书获取日期")
    SFZYJS: Mapped[str] = mapped_column(String(1), comment="是否专业教师")
    XZSSZYMC: Mapped[str | None] = mapped_column(String(60), comment="行政所属专业名称")
    XZSSZYDM: Mapped[str | None] = mapped_column(String(6), comment="行政所属专业代码")
    XZSSZYCC: Mapped[str | None] = mapped_column(String(10), comment="行政所属专业层次")
    XZSSZYDL: Mapped[str | None] = mapped_column(String(40), comment="行政所属专业大类")
    SFGGKJS: Mapped[str] = mapped_column(String(1), comment="是否公共课教师")
    SRGGKC: Mapped[str | None] = mapped_column(String(50), comment="所任公共课程")
    SFSZXJS: Mapped[str] = mapped_column(String(10), comment="是否为双师型教师")
    JXMS: Mapped[str] = mapped_column(String(10), comment="教学名师")
    SFZZSZKJS: Mapped[str] = mapped_column(String(1), comment="是否专职思政课教师")
    SFJZSZKJS: Mapped[str] = mapped_column(String(1), comment="是否兼职思政课教师")
    SFZZFDY: Mapped[str] = mapped_column(String(1), comment="是否专职辅导员")
    SFJZFDY: Mapped[str] = mapped_column(String(1), comment="是否兼职辅导员")
    SFZZXLJKJS: Mapped[str] = mapped_column(String(1), comment="是否专职心理健康教师")
    SFJZXLJKJS: Mapped[str] = mapped_column(String(1), comment="是否兼职心理健康教师")
    SFZYDTR: Mapped[str] = mapped_column(String(10), comment="是否专业带头人")
    ZYDTNX: Mapped[int | None] = mapped_column(comment="担任专业带头人年限")
    SFZYQFZR: Mapped[str] = mapped_column(String(10), comment="是否专业（群）负责人")
    ZYQFZRNX: Mapped[int | None] = mapped_column(comment="担任专业（群）负责人年限")
    CZHYQYGZNX: Mapped[Decimal] = mapped_column(Numeric(4, 1), comment="曾在行业企业工作年限")
    SJCJSJ: Mapped[str] = mapped_column(
        String(15), default=data_collection_timestamp, comment="数据采集时间"
    )
    TBR: Mapped[str | None] = mapped_column(String(36), comment="填报人")
    SJBS: Mapped[str | None] = mapped_column(String(32), comment="数据标识")
