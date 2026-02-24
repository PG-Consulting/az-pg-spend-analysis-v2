"""
Azure Functions entry point for Spend Analysis v3.
Registers all blueprints. Keep this file minimal — all logic lives in blueprints/ and src/.
"""
import logging

import azure.functions as func

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create main app
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Register blueprints
from blueprints.projects_bp import projects_bp
from blueprints.classification_bp import classification_bp
from blueprints.review_bp import review_bp
from blueprints.knowledge_bp import knowledge_bp
from blueprints.models_bp import models_bp
from blueprints.copilot_bp import copilot_bp
from blueprints.worker_bp import worker_bp

app.register_blueprint(projects_bp)
app.register_blueprint(classification_bp)
app.register_blueprint(review_bp)
app.register_blueprint(knowledge_bp)
app.register_blueprint(models_bp)
app.register_blueprint(copilot_bp)
app.register_blueprint(worker_bp)

logger.info("Spend Analysis v3 - All blueprints registered")
