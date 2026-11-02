from sqlalchemy import CheckConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.common import data_collection_timestamp, uuid_hex


class TeacherTraining(Base):
    __tablename__ = "ODS_XXJXSJ"
    ZJSJWYXBS: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=uuid_hex, comment="主键数据唯一性标识"
    )
    XXDM: Mapped[str] = mapped_column(String(10), comment="学校代码")

    __table_args__ = (
        UniqueConstraint("JGH", "JXPXMC", "JXPXLX", "JXPXDD", name="uq_ODS_XXJXSJ_training"),
        CheckConstraint('"PXTS" > 0', name="ck_ODS_XXJXSJ_PXTS_positive"),
    )

    JGH: Mapped[str] = mapped_column(String(20), comment="教工号")
    JSXM: Mapped[str] = mapped_column(String(36), comment="教师姓名")
    JSLB: Mapped[str] = mapped_column(String(20), comment="教师类别")
    YXBMCMC: Mapped[str] = mapped_column(String(60), comment="所属院系部/部门名称")
    JXPXMC: Mapped[str] = mapped_column(String(200), comment="项目名称")
    JXPXLX: Mapped[str] = mapped_column(String(20), comment="培训交流类型")
    JXPXFS: Mapped[str] = mapped_column(String(10), comment="培训形式")
    JBBMMC: Mapped[str] = mapped_column(String(100), comment="举办部门名称")
    JXPXJB: Mapped[str] = mapped_column(String(10), comment="培训交流级别")
    PXTS: Mapped[int] = mapped_column(comment="时长（天）")
    JXPXDD: Mapped[str] = mapped_column(String(100), comment="培训交流地点")
    PCBMMC: Mapped[str] = mapped_column(String(60), comment="派出部门名称")
    PCBMJB: Mapped[str] = mapped_column(String(10), comment="派出部门级别")
    SJCJSJ: Mapped[str] = mapped_column(
        String(15), default=data_collection_timestamp, comment="数据采集时间"
    )
    TBR: Mapped[str | None] = mapped_column(String(36), comment="填报人")
    SJBS: Mapped[str | None] = mapped_column(String(32), comment="数据标识")


class TeacherAward(Base):
    __tablename__ = "ODS_JSHJSJ"
    ZJSJWYXBS: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=uuid_hex, comment="主键数据唯一性标识"
    )
    XXDM: Mapped[str] = mapped_column(String(10), comment="学校代码")

    __table_args__ = (
        UniqueConstraint("DYHJRGH", "HJMC", "HJRQ", name="uq_ODS_JSHJSJ_award"),
        CheckConstraint(
            '"SFXQHZ" <> \'1\' OR "HZQYMC" IS NOT NULL',
            name="ck_ODS_JSHJSJ_HZQYMC_required",
        ),
    )

    DYHJRGH: Mapped[str] = mapped_column(String(20), comment="第一获奖人工号")
    DYHJRXM: Mapped[str] = mapped_column(String(36), comment="第一获奖人姓名")
    JSLB: Mapped[str] = mapped_column(String(20), comment="教师类别")
    YXBMCMC: Mapped[str] = mapped_column(String(60), comment="所属院系部/部门名称")
    HJMC: Mapped[str] = mapped_column(String(200), comment="获奖名称")
    JB: Mapped[str] = mapped_column(String(10), comment="级别")
    DJ: Mapped[str] = mapped_column(String(10), comment="等级")
    HJLB: Mapped[str] = mapped_column(String(20), comment="奖项类别")
    SFXQHZ: Mapped[str] = mapped_column(String(1), comment="是否校企合作")
    HZQYMC: Mapped[str | None] = mapped_column(String(200), comment="合作企业名称")
    BJDWMC: Mapped[str] = mapped_column(String(100), comment="颁奖单位名称")
    HJRQ: Mapped[str] = mapped_column(String(7), comment="获奖日期")
    HJRSC: Mapped[str] = mapped_column(String(10), comment="获奖人顺序")
    SFDYWCDW: Mapped[str] = mapped_column(String(1), comment="学校是否第一完成单位")
    SJCJSJ: Mapped[str] = mapped_column(
        String(15), default=data_collection_timestamp, comment="数据采集时间"
    )
    TBR: Mapped[str | None] = mapped_column(String(36), comment="填报人")
    SJBS: Mapped[str | None] = mapped_column(String(32), comment="数据标识")


class TeacherPublication(Base):
    __tablename__ = "ODS_LWZZSJ"
    ZJSJWYXBS: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=uuid_hex, comment="主键数据唯一性标识"
    )
    XXDM: Mapped[str] = mapped_column(String(10), comment="学校代码")

    __table_args__ = (UniqueConstraint("DYZGH", "ZZMC", "FBRQ", name="uq_ODS_LWZZSJ_publication"),)

    DYZGH: Mapped[str] = mapped_column(String(20), comment="第一作者工号")
    DYZXM: Mapped[str] = mapped_column(String(36), comment="第一作者姓名")
    JSLB: Mapped[str] = mapped_column(String(20), comment="教师类别")
    YXBMCMC: Mapped[str] = mapped_column(String(60), comment="所属院系部/部门名称")
    ZZMC: Mapped[str] = mapped_column(String(200), comment="著作名称")
    CGSX: Mapped[str] = mapped_column(String(10), comment="成果形式")
    LWFL: Mapped[str] = mapped_column(String(20), comment="著作与论文分类")
    CBSMC: Mapped[str] = mapped_column(String(180), comment="出版社或杂志社")
    FBRQ: Mapped[str] = mapped_column(String(7), comment="出版或发表日期")
    WCDWSC: Mapped[str] = mapped_column(String(10), comment="完成单位顺序")
    SJCJSJ: Mapped[str] = mapped_column(
        String(15), default=data_collection_timestamp, comment="数据采集时间"
    )
    TBR: Mapped[str | None] = mapped_column(String(36), comment="填报人")
    SJBS: Mapped[str | None] = mapped_column(String(32), comment="数据标识")


class EnterprisePractice(Base):
    __tablename__ = "ODS_JSQYJZSJSJ"
    ZJSJWYXBS: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=uuid_hex, comment="主键数据唯一性标识"
    )
    XXDM: Mapped[str] = mapped_column(String(10), comment="学校代码")

    __table_args__ = (
        UniqueConstraint("JGH", "QYDLLX", "JSDWMC", "GWMC", name="uq_ODS_JSQYJZSJSJ_practice"),
        CheckConstraint('"SJTS" > 0', name="ck_ODS_JSQYJZSJSJ_SJTS_positive"),
    )

    JGH: Mapped[str] = mapped_column(String(20), comment="教工号")
    JSXM: Mapped[str] = mapped_column(String(36), comment="教师姓名")
    JSLB: Mapped[str] = mapped_column(String(20), comment="教师类别")
    YXBMCMC: Mapped[str] = mapped_column(String(60), comment="所属院系部/部门名称")
    QYDLLX: Mapped[str] = mapped_column(String(20), comment="类型")
    JSDWMC: Mapped[str] = mapped_column(String(100), comment="接收单位名称")
    GWMC: Mapped[str] = mapped_column(String(60), comment="岗位名称")
    SJTS: Mapped[int] = mapped_column(comment="时长（天）")
    JSDDSZD: Mapped[str] = mapped_column(String(20), comment="接收单位所在地")
    PCBMMC: Mapped[str] = mapped_column(String(60), comment="派出（推荐）部门名称")
    PCBMJB: Mapped[str] = mapped_column(String(10), comment="派出（推荐）部门级别")
    SJCJSJ: Mapped[str] = mapped_column(
        String(15), default=data_collection_timestamp, comment="数据采集时间"
    )
    TBR: Mapped[str | None] = mapped_column(String(36), comment="填报人")
    SJBS: Mapped[str | None] = mapped_column(String(32), comment="数据标识")
