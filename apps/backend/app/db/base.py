# Imports all models so their tables register on Base.metadata.
# Used by Alembic's autogenerate and anything needing the full metadata —
# import this module instead of base_class when you need that side effect.
from app.db.base_class import Base  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.repository import Repository  # noqa: F401
from app.models.pull_request import PullRequest  # noqa: F401
from app.models.review import Review  # noqa: F401
