from __future__ import annotations

from sqlalchemy import and_, or_, select

from memorybook.extensions import db
from memorybook.models import (
    BookCategory,
    BookCollection,
    BookProduct,
    BookTemplate,
    ProjectAsset,
    ProjectPage,
    ProjectRevision,
    UserProject,
)


class CatalogRepository:
    @staticmethod
    def books_query(filters: dict):
        query = select(BookProduct).join(BookCategory, BookProduct.category_id == BookCategory.id).outerjoin(
            BookCollection,
            (BookProduct.collection_id == BookCollection.id)
            & BookCollection.is_active.is_(True)
            & BookCollection.deleted_at.is_(None),
        ).where(
            BookProduct.is_active.is_(True),
            BookProduct.deleted_at.is_(None),
            BookCategory.is_active.is_(True),
            BookCategory.deleted_at.is_(None),
        )
        if filters["search"]:
            term = f"%{filters['search']}%"
            query = query.where(
                or_(
                    BookProduct.title.ilike(term),
                    BookProduct.description.ilike(term),
                    BookCategory.name.ilike(term),
                    BookCollection.name.ilike(term),
                    BookProduct.style.ilike(term),
                    BookProduct.occasion.ilike(term),
                    BookProduct.book_type.ilike(term),
                )
            )
        if filters["category"]:
            query = query.where(
                or_(BookCategory.slug == filters["category"], BookCategory.name.ilike(filters["category"]))
            )
        if filters["collection"]:
            query = query.where(
                or_(BookCollection.slug == filters["collection"], BookCollection.name.ilike(filters["collection"]))
            )
        if filters["occasion"]:
            query = query.where(BookProduct.occasion.ilike(filters["occasion"]))
        if filters["style"]:
            query = query.where(BookProduct.style.ilike(filters["style"]))
        if filters["book_type"]:
            query = query.where(BookProduct.book_type.ilike(filters["book_type"]))
        if filters["featured"] is not None:
            query = query.where(BookProduct.is_featured.is_(filters["featured"]))
        if filters["page_count_min"] is not None:
            if filters["page_count_max"] is None:
                query = query.where(BookProduct.page_count_max >= filters["page_count_min"])
            else:
                query = query.where(
                    BookProduct.page_count_min <= filters["page_count_max"],
                    BookProduct.page_count_max >= filters["page_count_min"],
                )
        if filters["min_price"] is not None:
            query = query.where(BookProduct.starting_price >= filters["min_price"])
        if filters["max_price"] is not None:
            query = query.where(BookProduct.starting_price <= filters["max_price"])
        if filters["sort"] == "title":
            query = query.order_by(BookProduct.title.asc(), BookProduct.id.asc())
        elif filters["sort"] == "price-low":
            query = query.order_by(BookProduct.starting_price.asc(), BookProduct.id.asc())
        elif filters["sort"] == "price-high":
            query = query.order_by(BookProduct.starting_price.desc(), BookProduct.id.asc())
        elif filters["sort"] == "newest":
            query = query.order_by(BookProduct.created_at.desc(), BookProduct.id.asc())
        elif filters["sort"] == "pages":
            query = query.order_by(BookProduct.page_count_min.asc().nullslast(), BookProduct.title.asc())
        else:
            query = query.order_by(BookProduct.is_featured.desc(), BookProduct.title, BookProduct.id)
        return query

    @staticmethod
    def categories_query():
        return select(BookCategory).where(BookCategory.is_active.is_(True), BookCategory.deleted_at.is_(None)).order_by(
            BookCategory.sort_order, BookCategory.name
        )

    @staticmethod
    def collections_query():
        return select(BookCollection).join(
            BookCategory,
            (BookCollection.category_id == BookCategory.id)
            & BookCategory.is_active.is_(True)
            & BookCategory.deleted_at.is_(None),
        ).where(
            BookCollection.is_active.is_(True),
            BookCollection.deleted_at.is_(None),
        ).order_by(BookCollection.sort_order, BookCollection.name)

    @staticmethod
    def templates_query():
        published_products = select(BookProduct.id).join(
            BookCategory,
            (BookProduct.category_id == BookCategory.id)
            & BookCategory.is_active.is_(True)
            & BookCategory.deleted_at.is_(None),
        ).where(BookProduct.is_active.is_(True), BookProduct.deleted_at.is_(None))
        return select(BookTemplate).where(
            BookTemplate.is_active.is_(True),
            BookTemplate.deleted_at.is_(None),
            or_(
                BookTemplate.product_id.is_(None),
                and_(
                    BookTemplate.published_design_document.is_not(None),
                    BookTemplate.product_id.in_(published_products),
                ),
            ),
        ).order_by(BookTemplate.name)

    @staticmethod
    def owned_project(project_id: str, owner_id: str, *, lock: bool = False) -> UserProject | None:
        query = select(UserProject).where(
            UserProject.id == project_id,
            UserProject.user_id == owner_id,
            UserProject.status != "deleted",
        )
        if lock:
            query = query.with_for_update()
        return db.session.scalar(query)

    @staticmethod
    def owned_asset(project_id: str, asset_id: str) -> ProjectAsset | None:
        return db.session.scalar(
            select(ProjectAsset).where(ProjectAsset.project_id == project_id, ProjectAsset.id == asset_id)
        )

    @staticmethod
    def project_pages(project_id: str) -> list[ProjectPage]:
        return db.session.scalars(
            select(ProjectPage).where(ProjectPage.project_id == project_id).order_by(ProjectPage.page_number)
        ).all()

    @staticmethod
    def revisions(project_id: str) -> list[ProjectRevision]:
        return db.session.scalars(
            select(ProjectRevision).where(ProjectRevision.project_id == project_id).order_by(ProjectRevision.revision_number.desc())
        ).all()
