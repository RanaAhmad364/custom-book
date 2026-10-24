from flask import Blueprint

from memorybook.api.v1.auth.routes import auth_blueprint
from memorybook.api.v1.admin.routes import admin_blueprint
from memorybook.api.v1.assets import assets_blueprint
from memorybook.api.v1.catalog.routes import catalog_blueprint
from memorybook.api.v1.contracts.pdf import pdf_blueprint
from memorybook.api.v1.contracts.payments import payments_blueprint
from memorybook.api.v1.contracts.printing import print_blueprint
from memorybook.api.v1.health.routes import health_blueprint
from memorybook.api.v1.projects.routes import projects_blueprint


def create_v1_blueprint() -> Blueprint:
    versioned = Blueprint("api_v1", __name__, url_prefix="/api/v1")
    versioned.register_blueprint(health_blueprint)
    versioned.register_blueprint(auth_blueprint, url_prefix="/auth")
    versioned.register_blueprint(admin_blueprint, url_prefix="/admin")
    versioned.register_blueprint(catalog_blueprint)
    versioned.register_blueprint(assets_blueprint, url_prefix="/assets")
    versioned.register_blueprint(projects_blueprint, url_prefix="/projects")
    versioned.register_blueprint(print_blueprint, url_prefix="/print")
    versioned.register_blueprint(pdf_blueprint, url_prefix="/pdf")
    versioned.register_blueprint(payments_blueprint, url_prefix="/payments")

    legacy = Blueprint("legacy_api", __name__, url_prefix="/api")
    legacy.register_blueprint(print_blueprint, url_prefix="/print", name="legacy_print")
    legacy.register_blueprint(pdf_blueprint, url_prefix="/pdf", name="legacy_pdf")

    root = Blueprint("api_root", __name__)
    root.register_blueprint(versioned)
    root.register_blueprint(legacy)
    return root
