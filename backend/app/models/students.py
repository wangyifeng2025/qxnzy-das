from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.common import data_collection_timestamp, uuid_hex


class Student(Base):
    __tablename__ = "ODS_XSJBSJ"
    ZJSJWYXBS: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=uuid_hex, comment="主键数据唯一性标识"
    )
    XXDM: Mapped[str] = mapped_column(String(10), comment="学校代码")

    __table_args__ = (
        UniqueConstraint("XH", name="uq_ODS_XSJBSJ_XH"),
        CheckConstraint('"RXZF" >= 0', name="ck_ODS_XSJBSJ_RXZF_nonnegative"),
    )

    XH: Mapped[str] = mapped_column(String(20), comment="学号")
    XSXM: Mapped[str] = mapped_column(String(36), comment="姓名")
    XB: Mapped[str] = mapped_column(String(1), comment="性别")
    CSRQ: Mapped[str] = mapped_column(String(10), comment="出生日期")
    SFZJH: Mapped[str] = mapped_column(String(20), comment="身份证号（护照号）")
    ZZMM: Mapped[str] = mapped_column(String(20), comment="政治面貌")
    MZ: Mapped[str] = mapped_column(String(20), comment="民族")
    SYDGJDQ: Mapped[str] = mapped_column(String(60), comment="生源地国家（地区）")
    SYDSF: Mapped[str | None] = mapped_column(String(20), comment="生源地省份")
    SYDDS: Mapped[str | None] = mapped_column(String(40), comment="生源地地市")
    LYJD: Mapped[str] = mapped_column(String(20), comment="来自军队")
    SFCZHKZNC: Mapped[str] = mapped_column(String(1), comment="是否常住户口在农村")
    YXBMCMC: Mapped[str] = mapped_column(String(60), comment="所属院系部")
    ZYMC: Mapped[str] = mapped_column(String(60), comment="专业名称")
    ZYDM: Mapped[str] = mapped_column(
        String(6),
        ForeignKey("ODS_ZYSZSJ.ZYDM", ondelete="RESTRICT"),
        index=True,
        comment="专业代码",
    )
    ZYCCM: Mapped[str] = mapped_column(String(10), comment="专业层次")
    XZM: Mapped[str] = mapped_column(String(10), comment="学制")
    PYFSM: Mapped[str] = mapped_column(String(20), comment="培养方式")
    JTXS: Mapped[str | None] = mapped_column(String(200), comment="具体形式")
    NJ: Mapped[str] = mapped_column(String(10), comment="年级")
    BJMC: Mapped[str] = mapped_column(String(60), comment="班级名称")
    XJZT: Mapped[str] = mapped_column(String(20), comment="学籍状态")
    RXRQ: Mapped[str] = mapped_column(String(7), comment="入学日期")
    ZSFS: Mapped[str] = mapped_column(String(30), comment="招生方式")
    SYLXM: Mapped[str] = mapped_column(String(30), comment="生源类型")
    BYXXMC: Mapped[str] = mapped_column(String(100), comment="毕业学校名称")
    FSRYQK: Mapped[str | None] = mapped_column(String(20), comment="四辅人员情况")
    RXZF: Mapped[Decimal] = mapped_column(Numeric(9, 6), comment="入学总分")
    SFCJ: Mapped[str] = mapped_column(String(20), comment="是否残疾")
    SFJDLPKPH: Mapped[str] = mapped_column(String(1), comment="是否建档立卡贫困户")
    SFTXXZ: Mapped[str] = mapped_column(String(1), comment="是否弹性学制")
    SJCJSJ: Mapped[str] = mapped_column(
        String(15), default=data_collection_timestamp, comment="数据采集时间"
    )
    TBR: Mapped[str | None] = mapped_column(String(36), comment="填报人")
    SJBS: Mapped[str | None] = mapped_column(String(32), comment="数据标识")


class SeptemberNewStudent(Base):
    __tablename__ = "ODS_XSXSSJ"
    ZJSJWYXBS: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=uuid_hex, comment="主键数据唯一性标识"
    )
    XXDM: Mapped[str] = mapped_column(String(10), comment="学校代码")

    __table_args__ = (
        UniqueConstraint("XH", name="uq_ODS_XSXSSJ_XH"),
        CheckConstraint('"RXZF" >= 0', name="ck_ODS_XSXSSJ_RXZF_nonnegative"),
    )

    XH: Mapped[str] = mapped_column(String(20), comment="学号")
    XSXM: Mapped[str] = mapped_column(String(36), comment="姓名")
    XB: Mapped[str] = mapped_column(String(1), comment="性别")
    CSRQ: Mapped[str] = mapped_column(String(10), comment="出生日期")
    SFZJH: Mapped[str] = mapped_column(String(20), comment="身份证号")
    ZZMM: Mapped[str] = mapped_column(String(20), comment="政治面貌")
    MZ: Mapped[str] = mapped_column(String(20), comment="民族")
    SYDGJDQ: Mapped[str] = mapped_column(String(60), comment="生源地国家（地区）")
    SYDSF: Mapped[str | None] = mapped_column(String(20), comment="生源地省份")
    SYDDS: Mapped[str | None] = mapped_column(String(40), comment="生源地地市")
    LYJD: Mapped[str] = mapped_column(String(20), comment="来自军队")
    SFCZHKZNC: Mapped[str] = mapped_column(String(1), comment="是否常住户口在农村")
    YXBMCMC: Mapped[str] = mapped_column(String(60), comment="所属院系部")
    ZYMC: Mapped[str] = mapped_column(String(60), comment="专业名称")
    ZYDM: Mapped[str] = mapped_column(
        String(6),
        ForeignKey("ODS_ZYSZSJ.ZYDM", ondelete="RESTRICT"),
        index=True,
        comment="专业代码",
    )
    ZYCCM: Mapped[str] = mapped_column(String(10), comment="专业层次")
    XZM: Mapped[str] = mapped_column(String(10), comment="学制")
    PYFSM: Mapped[str] = mapped_column(String(20), comment="培养方式")
    JTXS: Mapped[str | None] = mapped_column(String(200), comment="具体形式")
    NJ: Mapped[str] = mapped_column(String(10), comment="年级")
    BJMC: Mapped[str] = mapped_column(String(60), comment="班级名称")
    XJZT: Mapped[str] = mapped_column(String(20), comment="学籍状态")
    RXRQ: Mapped[str] = mapped_column(String(7), comment="入学日期")
    ZSFS: Mapped[str] = mapped_column(String(30), comment="招生方式")
    SYLXM: Mapped[str] = mapped_column(String(30), comment="生源类型")
    BYXXMC: Mapped[str] = mapped_column(String(100), comment="毕业学校名称")
    FSRYQK: Mapped[str | None] = mapped_column(String(20), comment="四辅人员情况")
    RXZF: Mapped[Decimal] = mapped_column(Numeric(9, 6), comment="入学总分")
    DYZSPC: Mapped[str] = mapped_column(String(100), comment="对应招生批次")
    LB: Mapped[str] = mapped_column(String(50), comment="类别")
    KML: Mapped[str] = mapped_column(String(20), comment="科目类")
    WHKZX: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 3), comment="对应招生批次文化最低控制线"
    )
    ZYKZX: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 3), comment="对应招生批次专业最低控制线"
    )
    SFCJ: Mapped[str] = mapped_column(String(20), comment="是否残疾")
    SFJDLPKPH: Mapped[str] = mapped_column(String(1), comment="是否建档立卡贫困户")
    SJCJSJ: Mapped[str] = mapped_column(
        String(15), default=data_collection_timestamp, comment="数据采集时间"
    )
    TBR: Mapped[str | None] = mapped_column(String(36), comment="填报人")
    SJBS: Mapped[str | None] = mapped_column(String(32), comment="数据标识")
