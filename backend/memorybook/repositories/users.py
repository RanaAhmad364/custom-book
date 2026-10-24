from memorybook.extensions import db
from memorybook.models import User


class UserRepository:
    @staticmethod
    def get_by_email(email: str) -> User | None:
        return db.session.scalar(db.select(User).where(User.email == email))

    @staticmethod
    def get_by_id(user_id: str) -> User | None:
        return db.session.get(User, user_id)

    @staticmethod
    def get_by_email_for_update(email: str) -> User | None:
        return db.session.scalar(db.select(User).where(User.email == email).with_for_update())

    @staticmethod
    def add(user: User) -> User:
        db.session.add(user)
        db.session.flush()
        return user
