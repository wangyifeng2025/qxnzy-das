from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.common import data_collection_timestamp, uuid_hex


class Major(Base):
    __tablename__ = "ODS_ZYSZSJ"
    ZJSJWYXBS: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=uuid_hex, comment="主键数据唯一性标识"
    )
    XXDM: Mapped[str] = mapped_column(String(10), comment="学校代码")

    __table_args__ = (
        UniqueConstraint("ZYDM", name="uq_ODS_ZYSZSJ_ZYDM"),
        UniqueConstraint("ZYMC", name="uq_ODS_ZYSZSJ_ZYMC"),
        CheckConstraint("\"ZYDM\" ~ '^[0-9]{6}$'", name="ck_ODS_ZYSZSJ_ZYDM_format"),
        CheckConstraint(
            "\"PZSZNY\" ~ '^[0-9]{4}-(0[1-9]|1[0-2])$' AND "
            "\"SCZSNY\" ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'",
            name="ck_ODS_ZYSZSJ_NY_format",
        ),
        CheckConstraint('"PZSZNY" <= "SCZSNY"', name="ck_ODS_ZYSZSJ_NY_order"),
        CheckConstraint(
            '"SFZDZY" <> \'1\' OR ("ZDZYJBM" IS NOT NULL AND "ZDZYLXM" IS NOT NULL)',
            name="ck_ODS_ZYSZSJ_ZDZY_required",
        ),
        CheckConstraint(
            '"ZYCCM" <> \'1\' OR "SYXWLBM" IS NOT NULL',
            name="ck_ODS_ZYSZSJ_SYXWLBM_required",
        ),
    )

    ZYMC: Mapped[str] = mapped_column(String(60), comment="专业名称")
    ZYDM: Mapped[str] = mapped_column(String(6), comment="专业代码")
    ZYCCM: Mapped[str] = mapped_column(String(10), comment="专业层次")
    XZM: Mapped[str] = mapped_column(String(10), comment="学制")
    ZYDLMC: Mapped[str] = mapped_column(String(40), comment="专业大类")
    ZYFLMC: Mapped[str] = mapped_column(String(40), comment="专业类")
    PZSZNY: Mapped[str] = mapped_column(String(7), comment="批准设置日期")
    SCZSNY: Mapped[str] = mapped_column(String(7), comment="首次招生日期")
    ZYSSYXBMC: Mapped[str] = mapped_column(String(60), comment="专业所属院系部")
    SYXWLBM: Mapped[str | None] = mapped_column(String(20), comment="学位授予门类")
    SFZDZY: Mapped[str] = mapped_column(String(1), comment="是否重点专业")
    ZDZYJBM: Mapped[str | None] = mapped_column(String(10), comment="重点专业级别")
    ZDZYLXM: Mapped[str | None] = mapped_column(String(100), comment="重点专业类型")
    ZYPPCYQK: Mapped[str] = mapped_column(String(40), comment="专业匹配地方产业情况")
    CYMC: Mapped[str | None] = mapped_column(String(200), comment="产业名称")
    GNDW: Mapped[str | None] = mapped_column(String(100), comment="功能定位")
    ZYJYDLMC: Mapped[str] = mapped_column(String(100), comment="职业类别大类名称")
    ZYJYFLMC: Mapped[str] = mapped_column(String(100), comment="职业类别中类名称")
    ZYJYXLMC: Mapped[str] = mapped_column(String(200), comment="职业类别小类名称")
    SJCJSJ: Mapped[str] = mapped_column(
        String(15), default=data_collection_timestamp, comment="数据采集时间"
    )
    TBR: Mapped[str | None] = mapped_column(String(36), comment="填报人")
    SJBS: Mapped[str | None] = mapped_column(String(32), comment="数据标识")


class Course(Base):
    __tablename__ = "ODS_KCJBSJ"
    ZJSJWYXBS: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=uuid_hex, comment="主键数据唯一性标识"
    )
    XXDM: Mapped[str] = mapped_column(String(10), comment="学校代码")

    __table_args__ = (
        UniqueConstraint("ZYDM", "NJ", "KCH", name="uq_ODS_KCJBSJ_ZYDM_NJ_KCH"),
        CheckConstraint('"KZZXS" > 0', name="ck_ODS_KCJBSJ_KZZXS_positive"),
        CheckConstraint(
            '"SJJXKSS" >= 0 AND "SJJXKSS" <= "KZZXS"',
            name="ck_ODS_KCJBSJ_SJJXKSS_range",
        ),
        CheckConstraint(
            '"SFXQHZKFKC" <> \'1\' OR "HZQYMC" IS NOT NULL',
            name="ck_ODS_KCJBSJ_HZQYMC_required",
        ),
        CheckConstraint(
            "\"KKXQM\" ~ '^[0-9]{4}-[0-9]{4}-[12]学期$'",
            name="ck_ODS_KCJBSJ_KKXQM_format",
        ),
        Index("ix_ODS_KCJBSJ_KCH", "KCH"),
    )

    ZYMC: Mapped[str] = mapped_column(String(60), comment="专业名称")
    ZYDM: Mapped[str] = mapped_column(
        String(6), ForeignKey("ODS_ZYSZSJ.ZYDM", ondelete="RESTRICT"), comment="专业代码"
    )
    ZYCCM: Mapped[str] = mapped_column(String(10), comment="专业层次")
    XZM: Mapped[str] = mapped_column(String(10), comment="学制")
    PYFSM: Mapped[str] = mapped_column(String(20), comment="培养方式")
    JTXS: Mapped[str | None] = mapped_column(String(200), comment="具体形式")
    SYLXM: Mapped[str] = mapped_column(String(200), comment="生源类型")
    NJ: Mapped[str] = mapped_column(String(10), comment="年级")
    KCMC: Mapped[str] = mapped_column(String(60), comment="课程名称")
    KCH: Mapped[str] = mapped_column(String(20), comment="课程代码")
    KCLXM: Mapped[str] = mapped_column(String(10), comment="课程类型")
    KCSXM: Mapped[str] = mapped_column(String(20), comment="课程属性")
    GGKC: Mapped[str | None] = mapped_column(String(30), comment="公共基础课程")
    ZYKC: Mapped[str | None] = mapped_column(String(30), comment="专业课程")
    KCXZM: Mapped[str] = mapped_column(String(10), comment="课程性质")
    KKXQM: Mapped[str] = mapped_column(String(20), comment="开课学期")
    KKDWMC: Mapped[str] = mapped_column(String(60), comment="开课单位名称")
    SFXQHZKFKC: Mapped[str] = mapped_column(String(1), comment="是否校企合作开发课程")
    HZQYMC: Mapped[str | None] = mapped_column(String(200), comment="合作企业名称")
    ZXJPC: Mapped[str] = mapped_column(String(10), comment="在线精品课程")
    SFKZRTKC: Mapped[str] = mapped_column(String(1), comment="是否课证融通课程")
    SFWLJXKC: Mapped[str] = mapped_column(String(1), comment="是否网络教学课程")
    KCSZSFK: Mapped[str] = mapped_column(String(10), comment="课程思政示范课")
    KZZXS: Mapped[int] = mapped_column(comment="课程总学时")
    SJJXKSS: Mapped[int] = mapped_column(comment="实践教学学时")
    SJCJSJ: Mapped[str] = mapped_column(
        String(15), default=data_collection_timestamp, comment="数据采集时间"
    )
    TBR: Mapped[str | None] = mapped_column(String(36), comment="填报人")
    SJBS: Mapped[str | None] = mapped_column(String(32), comment="数据标识")


class TeachingAssignment(Base):
    __tablename__ = "ODS_SKXXSJ"
    ZJSJWYXBS: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=uuid_hex, comment="主键数据唯一性标识"
    )
    XXDM: Mapped[str] = mapped_column(String(10), comment="学校代码")

    __table_args__ = (
        ForeignKeyConstraint(
            ("ZYDM", "NJ", "KCH"),
            ("ODS_KCJBSJ.ZYDM", "ODS_KCJBSJ.NJ", "ODS_KCJBSJ.KCH"),
            name="fk_ODS_SKXXSJ_course",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "JGH",
            "KCH",
            "BJMC",
            "SKXQM",
            "CSMC",
            name="uq_ODS_SKXXSJ_teaching_assignment",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint('"BCSKSS" > 0 AND "JXGZL" > 0', name="ck_ODS_SKXXSJ_workload_positive"),
        CheckConstraint('"XSKSS" >= 0 AND "XSKSS" <= "BCSKSS"', name="ck_ODS_SKXXSJ_XSKSS_range"),
        Index("ix_ODS_SKXXSJ_course", "ZYDM", "NJ", "KCH"),
    )

    JGH: Mapped[str] = mapped_column(String(20), comment="授课教师工号")
    JSXM: Mapped[str] = mapped_column(String(36), comment="授课教师姓名")
    JSLB: Mapped[str] = mapped_column(String(20), comment="教师类别")
    ZYMC: Mapped[str] = mapped_column(String(60), comment="专业名称")
    ZYDM: Mapped[str] = mapped_column(
        String(6), ForeignKey("ODS_ZYSZSJ.ZYDM", ondelete="RESTRICT"), comment="专业代码"
    )
    ZYCCM: Mapped[str] = mapped_column(String(10), comment="专业层次")
    XZM: Mapped[str] = mapped_column(String(10), comment="学制")
    PYFSM: Mapped[str] = mapped_column(String(20), comment="培养方式")
    JTXS: Mapped[str | None] = mapped_column(String(200), comment="具体形式")
    SYLXM: Mapped[str] = mapped_column(String(100), comment="生源类型")
    NJ: Mapped[str] = mapped_column(String(10), comment="授课年级")
    KCMC: Mapped[str] = mapped_column(String(60), comment="课程名称")
    KCH: Mapped[str] = mapped_column(String(20), comment="课程代码")
    SKXQM: Mapped[str] = mapped_column(String(20), comment="授课学期")
    KKDWMC: Mapped[str] = mapped_column(String(60), comment="开课单位名称")
    SKRW: Mapped[str] = mapped_column(String(10), comment="授课任务")
    CSWZ: Mapped[str] = mapped_column(String(10), comment="场所位置")
    CSMC: Mapped[str | None] = mapped_column(String(60), comment="场所名称")
    CSMPH: Mapped[str | None] = mapped_column(String(20), comment="场所门牌号")
    SZLYMC: Mapped[str | None] = mapped_column(String(60), comment="所在楼宇名称")
    SZXQMC: Mapped[str | None] = mapped_column(String(60), comment="所在校区")
    BJMC: Mapped[str] = mapped_column(String(60), comment="班级名称")
    BCSKSS: Mapped[Decimal] = mapped_column(Numeric(6, 1), comment="本场所教学课时数")
    XSKSS: Mapped[Decimal] = mapped_column(Numeric(6, 1), comment="线上教学课时数")
    JXGZL: Mapped[Decimal] = mapped_column(Numeric(6, 1), comment="教师教学工作量")
    SJCJSJ: Mapped[str] = mapped_column(
        String(15), default=data_collection_timestamp, comment="数据采集时间"
    )
    TBR: Mapped[str | None] = mapped_column(String(36), comment="填报人")
    SJBS: Mapped[str | None] = mapped_column(String(32), comment="数据标识")
