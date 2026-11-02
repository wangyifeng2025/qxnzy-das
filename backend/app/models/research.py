from decimal import Decimal

from sqlalchemy import CheckConstraint, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.common import data_collection_timestamp, uuid_hex


class ResearchProject(Base):
    __tablename__ = "ODS_KYXMJBSJ"
    ZJSJWYXBS: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=uuid_hex, comment="主键数据唯一性标识"
    )
    XXDM: Mapped[str] = mapped_column(String(10), comment="学校代码")

    __table_args__ = (
        UniqueConstraint("DYZCRGH", "KTMC", "LXRQ", name="uq_ODS_KYXMJBSJ_project"),
        CheckConstraint('"LXJF" >= 0 AND "LJDKJE" >= 0', name="ck_ODS_KYXMJBSJ_amount_nonnegative"),
        CheckConstraint('"JXRQ" IS NULL OR "JXRQ" >= "LXRQ"', name="ck_ODS_KYXMJBSJ_date_order"),
        CheckConstraint(
            '"SFXQHZWC" <> \'1\' OR "HZQYMC" IS NOT NULL',
            name="ck_ODS_KYXMJBSJ_HZQYMC_required",
        ),
    )

    DYZCRGH: Mapped[str] = mapped_column(String(20), comment="第一主持人工号")
    DYZCRXM: Mapped[str] = mapped_column(String(36), comment="第一主持人姓名")
    JSLB: Mapped[str] = mapped_column(String(20), comment="教师类别")
    YXBMCMC: Mapped[str] = mapped_column(String(60), comment="所属院系部/部门名称")
    KTMC: Mapped[str] = mapped_column(String(300), comment="课题名称")
    KTFL: Mapped[str] = mapped_column(String(20), comment="课题分类")
    KTXZ: Mapped[str] = mapped_column(String(20), comment="课题性质")
    YJZT: Mapped[str] = mapped_column(String(10), comment="研究状态")
    KTLY: Mapped[str] = mapped_column(String(20), comment="课题来源")
    PZBMMC: Mapped[str] = mapped_column(String(100), comment="批准部门名称")
    KTJB: Mapped[str] = mapped_column(String(10), comment="课题级别")
    LXRQ: Mapped[str] = mapped_column(String(7), comment="立项日期")
    JFLY: Mapped[str] = mapped_column(String(20), comment="经费来源")
    LXJF: Mapped[Decimal] = mapped_column(Numeric(18, 4), comment="立项经费")
    JXRQ: Mapped[str | None] = mapped_column(String(7), comment="结项日期")
    JDBM: Mapped[str | None] = mapped_column(String(100), comment="鉴定部门")
    JDJG: Mapped[str | None] = mapped_column(String(10), comment="鉴定结果")
    LJDKJE: Mapped[Decimal] = mapped_column(Numeric(18, 4), comment="累计到款金额")
    SFXQHZWC: Mapped[str] = mapped_column(String(1), comment="是否校企合作完成")
    HZQYMC: Mapped[str | None] = mapped_column(String(200), comment="合作完成企业名称")
    CYJSS: Mapped[int] = mapped_column(comment="参与教师人数")
    SJCJSJ: Mapped[str] = mapped_column(
        String(15), default=data_collection_timestamp, comment="数据采集时间"
    )
    TBR: Mapped[str | None] = mapped_column(String(36), comment="填报人")
    SJBS: Mapped[str | None] = mapped_column(String(32), comment="数据标识")


class HorizontalResearchProject(Base):
    __tablename__ = "ODS_HXKTSJ"
    ZJSJWYXBS: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=uuid_hex, comment="主键数据唯一性标识"
    )
    XXDM: Mapped[str] = mapped_column(String(10), comment="学校代码")

    __table_args__ = (
        UniqueConstraint("DYZCRGH", "KTMC", "LXRQ", name="uq_ODS_HXKTSJ_project"),
        CheckConstraint(
            '"BXNDKJE" >= 0 AND "LJDKJE" >= 0 AND "LJDKJE" >= "BXNDKJE"',
            name="ck_ODS_HXKTSJ_amount_logic",
        ),
        CheckConstraint('"JXRQ" IS NULL OR "JXRQ" >= "LXRQ"', name="ck_ODS_HXKTSJ_date_order"),
        CheckConstraint(
            '"SFXQHZWC" <> \'1\' OR "HZQYMC" IS NOT NULL',
            name="ck_ODS_HXKTSJ_HZQYMC_required",
        ),
    )

    DYZCRGH: Mapped[str] = mapped_column(String(20), comment="第一主持人工号")
    DYZCRXM: Mapped[str] = mapped_column(String(36), comment="第一主持人姓名")
    JSLB: Mapped[str] = mapped_column(String(20), comment="教师类别")
    YXBMCMC: Mapped[str] = mapped_column(String(60), comment="所属院系部/部门名称")
    KTMC: Mapped[str] = mapped_column(String(300), comment="课题名称")
    YJZT: Mapped[str] = mapped_column(String(10), comment="研究状态")
    KTLY: Mapped[str] = mapped_column(String(20), comment="课题来源")
    SFLYXQHZQY: Mapped[str] = mapped_column(String(1), comment="是否来源校企合作企业")
    WTFMC: Mapped[str] = mapped_column(String(100), comment="委托方名称")
    LXRQ: Mapped[str] = mapped_column(String(7), comment="立项日期")
    BXNDKJE: Mapped[Decimal] = mapped_column(Numeric(18, 4), comment="本学年到账金额")
    JXRQ: Mapped[str | None] = mapped_column(String(7), comment="结项日期")
    JDBM: Mapped[str | None] = mapped_column(String(100), comment="鉴定部门")
    JDJG: Mapped[str | None] = mapped_column(String(10), comment="鉴定结果")
    LJDKJE: Mapped[Decimal] = mapped_column(Numeric(18, 4), comment="累计到账金额")
    SFXQHZWC: Mapped[str] = mapped_column(String(1), comment="是否校企合作完成")
    HZQYMC: Mapped[str | None] = mapped_column(String(200), comment="合作完成企业名称")
    FWLX: Mapped[str] = mapped_column(String(20), comment="服务类型")
    SJCJSJ: Mapped[str] = mapped_column(
        String(15), default=data_collection_timestamp, comment="数据采集时间"
    )
    TBR: Mapped[str | None] = mapped_column(String(36), comment="填报人")
    SJBS: Mapped[str | None] = mapped_column(String(32), comment="数据标识")


class IntellectualProperty(Base):
    __tablename__ = "ODS_ZSCQSJ"
    ZJSJWYXBS: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=uuid_hex, comment="主键数据唯一性标识"
    )
    XXDM: Mapped[str] = mapped_column(String(10), comment="学校代码")

    __table_args__ = (
        UniqueConstraint("ZSCQBH", name="uq_ODS_ZSCQSJ_ZSCQBH"),
        CheckConstraint('"ZRXKJE" >= 0', name="ck_ODS_ZSCQSJ_ZRXKJE_nonnegative"),
        CheckConstraint(
            '"ZRXKJE" <= 0 OR ("SRFMC" IS NOT NULL AND "ZRXKRQ" IS NOT NULL)',
            name="ck_ODS_ZSCQSJ_transfer_required",
        ),
        CheckConstraint(
            '"SFXQHZWC" <> \'1\' OR "HZQYMC" IS NOT NULL',
            name="ck_ODS_ZSCQSJ_HZQYMC_required",
        ),
    )

    DYFMRGH: Mapped[str] = mapped_column(String(20), index=True, comment="第一发明人工号")
    DYFMRXM: Mapped[str] = mapped_column(String(36), comment="第一发明人姓名")
    JSLB: Mapped[str] = mapped_column(String(20), comment="教师类别")
    YXBMCMC: Mapped[str] = mapped_column(String(60), comment="所属院系部/部门名称")
    ZSCQMC: Mapped[str] = mapped_column(String(200), comment="知识产权项目名称")
    ZSCQBH: Mapped[str] = mapped_column(String(32), comment="知识产权项目名称编号")
    XMLX: Mapped[str] = mapped_column(String(20), comment="项目类型")
    HDRQ: Mapped[str] = mapped_column(String(7), comment="获得日期")
    SFXQHZWC: Mapped[str] = mapped_column(String(1), comment="是否校企合作完成")
    HZQYMC: Mapped[str | None] = mapped_column(String(200), comment="合作完成企业名称")
    ZRXKJE: Mapped[Decimal] = mapped_column(Numeric(18, 4), comment="转让/许可金额")
    SRFMC: Mapped[str | None] = mapped_column(String(100), comment="受让方名称")
    ZRXKRQ: Mapped[str | None] = mapped_column(String(7), comment="转让/许可日期")
    SJCJSJ: Mapped[str] = mapped_column(
        String(15), default=data_collection_timestamp, comment="数据采集时间"
    )
    TBR: Mapped[str | None] = mapped_column(String(36), comment="填报人")
    SJBS: Mapped[str | None] = mapped_column(String(32), comment="数据标识")
