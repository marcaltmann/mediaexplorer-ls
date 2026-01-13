import enum
from typing import Optional
from urllib.parse import urljoin
from uuid import UUID, uuid4

from litestar.plugins.sqlalchemy import base
from sqlalchemy import ForeignKey, func, text, select, String, Text, JSON, Boolean, Enum
from sqlalchemy import Column
from sqlalchemy import Table
from sqlalchemy import Integer

from sqlalchemy.orm import Mapped, mapped_column, relationship

from explorer.config import Settings

settings = Settings.from_env()


association_table = Table(
    'association_table',
    base.BigIntAuditBase.metadata,
    Column('resource_id', ForeignKey('resource.id'), primary_key=True),
    Column('category_id', ForeignKey('category.id'), primary_key=True),
)


class Collection(base.BigIntAuditBase):
    __tablename__ = 'collection'
    name: Mapped[str]
    uuid: Mapped[UUID] = mapped_column(default=uuid4, nullable=False)
    description: Mapped[str] = mapped_column(default='', nullable=False)
    color: Mapped[str] = mapped_column(String(7), default='#333333', nullable=False)
    resources: Mapped[list[Resource]] = relationship(
        back_populates='collection', lazy='selectin'
    )

    def __repr__(self):
        return f"Collection(id={self.id}, name='{self.name}')"


class License(enum.Enum):
    cc0 = 0
    by = 1
    by_sa = 2
    by_nd = 3
    by_nc = 4
    by_nc_sa = 5
    by_nc_nd = 6
    private = 7
    other = 8
    unknown = 9


class Resource(base.BigIntAuditBase):
    __tablename__ = 'resource'
    name: Mapped[str]
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default='')
    uuid: Mapped[UUID] = mapped_column(default=uuid4, nullable=False)
    license: Mapped[License] = mapped_column(Enum(License), server_default='private')
    is_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text('false')
    )
    toc: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey('collection.id'))
    collection: Mapped[Collection] = relationship(
        lazy='joined', innerjoin=True, viewonly=True
    )
    categories: Mapped[list[Category]] = relationship(
        secondary=association_table, back_populates='resources'
    )
    media_file: Mapped[MediaFile] = relationship(
        back_populates='resource', lazy='selectin', uselist=False
    )

    def is_video(self) -> bool:
        return True

    def is_audio(self) -> bool:
        return False

    def get_thumb_url(self, size: str) -> str:
        if self.media_file is None:
            return ''
        else:
            return self.media_file.get_thumb_url(size)

    @property
    def duration(self) -> float:
        if self.media_file is None:
            return 0.0
        else:
            return self.media_file.duration

    @property
    def size(self) -> float:
        return 0.0

    def __repr__(self) -> str:
        return f"Resource(id={self.id}, uuid='{self.uuid}' name='{self.name}')"


class MediaType(enum.Enum):
    video = 0
    audio = 1
    image = 2


class MediaFile(base.BigIntAuditBase):
    __tablename__ = 'media_file'
    filename: Mapped[str]
    type: Mapped[MediaType] = mapped_column(Enum(MediaType), server_default='video')
    url: Mapped[str] = mapped_column(server_default='')
    poster_url: Mapped[str] = mapped_column(server_default='')
    uuid: Mapped[UUID] = mapped_column(default=uuid4, nullable=False)
    sub_type: Mapped[Optional[str]] = mapped_column(server_default='')
    size: Mapped[Optional[int]] = mapped_column(server_default=text('0'))
    duration: Mapped[float] = mapped_column(server_default=text('0'))
    waveform: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    preview_images: Mapped[dict] = mapped_column(JSON, nullable=True)
    resource_id: Mapped[int] = mapped_column(ForeignKey('resource.id'))
    resource: Mapped[Resource] = relationship(
        lazy='joined', innerjoin=True, viewonly=True
    )

    def get_media_type(self) -> str:
        return f'{self.type.name}/{self.sub_type}'

    def is_video(self) -> bool:
        return self.type == MediaType.video

    def is_audio(self) -> bool:
        return self.type == MediaType.audio

    def get_url(self) -> str:
        bucket_url = settings.s3.get_bucket_url()
        return f'{bucket_url}/{self.filename}'

    def get_thumb_url(self, size: str) -> str:
        bucket_url = settings.s3.get_bucket_url()
        return f'{bucket_url}/{self.uuid}/thumb-{size}.webp'

    def __repr__(self) -> str:
        return (
            f"MediaFile(id={self.id}, uuid='{self.uuid}', filename='{self.filename}')"
        )


""" class PosterImage(base.BigIntAuditBase):
    __tablename__ = 'poster_image'
    filename: Mapped[str]
    media_type: Mapped[str]
    web_variants: Mapped[dict] = mapped_column(JSON, nullable=True)
    media_file_id: Mapped[int] = mapped_column(ForeignKey('media_file.id'))
    media_file: Mapped[Resource] = relationship(
        lazy='joined', innerjoin=True, viewonly=True
    )

    def __repr__(self) -> str:
        return (
            f"PosterImage(id={self.id}, filename='{self.filename}', media_type='{self.media_type}')"
        )
 """


class DerivativeType(enum.Enum):
    video_720p = 0
    video_480p = 1
    audio_128k = 2
    poster_hd = 3
    thumbnail_480 = 4
    thumbnail_320 = 5
    thumbnail_160 = 6


class DerivativeFile(base.UUIDv7AuditBase):
    """Seems to be too implicit."""

    __tablename__ = 'derivative_file'
    type: Mapped[DerivativeType] = mapped_column(
        Enum(DerivativeType), server_default='video_720p'
    )
    media_type: Mapped[str]
    media_file_id: Mapped[int] = mapped_column(ForeignKey('media_file.id'))
    media_file: Mapped[MediaFile] = relationship(
        lazy='joined', innerjoin=True, viewonly=True
    )
    is_stored: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text('false')
    )

    def __repr__(self):
        return f"DerivativeFile(id={self.id}, type='{self.type.name}', media_type='{self.media_type}')"


class Category(base.BigIntAuditBase):
    __tablename__ = 'category'

    name: Mapped[str]
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default='')
    wikidata_id: Mapped[Optional[str]] = mapped_column(server_default='')
    resources: Mapped[list[Resource]] = relationship(
        secondary=association_table, back_populates='categories'
    )

    def __repr__(self) -> str:
        return f"Category(id={self.id}, name='{self.name}')"
