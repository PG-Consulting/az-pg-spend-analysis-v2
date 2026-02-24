"""Shared fixtures for Spend Analysis v3 tests."""

import uuid
import pytest
from datetime import datetime, timezone


@pytest.fixture
def tmp_models_dir(tmp_path):
    """Creates a temporary models directory structure with required subdirectories."""
    models_dir = tmp_path / "models"
    (models_dir / "sectors").mkdir(parents=True)
    (models_dir / "projects").mkdir(parents=True)
    (models_dir / "taxonomy_jobs").mkdir(parents=True)
    return str(models_dir)


@pytest.fixture
def sample_hierarchy():
    """
    Returns a realistic naval/procurement hierarchy as a list of dicts.

    Structure (3 N1s, ~2-3 N2s each, ~2-3 N3s, ~2-3 N4s per N3):
      - Materiais
          - Componentes Mecanicos
              - Fixacao
                  - Parafusos
                  - Porcas
              - Vedacao
                  - Aneis O-Ring
                  - Juntas Metalicas
          - Componentes Eletricos
              - Cabos e Condutores
                  - Cabos de Potencia
                  - Cabos de Instrumentacao
              - Conectores
                  - Conectores Circulares
      - Servicos
          - Manutencao
              - Manutencao Preventiva
                  - Inspecao Programada
                  - Troca de Filtros
              - Manutencao Corretiva
                  - Reparo de Motor
                  - Reparo de Bomba
          - Engenharia
              - Projetos
                  - Projeto Naval
                  - Projeto Estrutural
      - Equipamentos
          - Propulsao
              - Motores Principais
                  - Motor Diesel Maritimo
                  - Motor a Gas
              - Sistemas Auxiliares
                  - Bomba de Combustivel
                  - Trocador de Calor
          - Navegacao
              - Instrumentos
                  - Radar Maritimo
                  - GPS Diferencial
    """
    hierarchy = [
        # --- Materiais ---
        {"N1": "Materiais", "N2": "Componentes Mecanicos", "N3": "Fixacao", "N4": "Parafusos"},
        {"N1": "Materiais", "N2": "Componentes Mecanicos", "N3": "Fixacao", "N4": "Porcas"},
        {"N1": "Materiais", "N2": "Componentes Mecanicos", "N3": "Vedacao", "N4": "Aneis O-Ring"},
        {"N1": "Materiais", "N2": "Componentes Mecanicos", "N3": "Vedacao", "N4": "Juntas Metalicas"},
        {"N1": "Materiais", "N2": "Componentes Eletricos", "N3": "Cabos e Condutores", "N4": "Cabos de Potencia"},
        {"N1": "Materiais", "N2": "Componentes Eletricos", "N3": "Cabos e Condutores", "N4": "Cabos de Instrumentacao"},
        {"N1": "Materiais", "N2": "Componentes Eletricos", "N3": "Conectores", "N4": "Conectores Circulares"},
        # --- Servicos ---
        {"N1": "Servicos", "N2": "Manutencao", "N3": "Manutencao Preventiva", "N4": "Inspecao Programada"},
        {"N1": "Servicos", "N2": "Manutencao", "N3": "Manutencao Preventiva", "N4": "Troca de Filtros"},
        {"N1": "Servicos", "N2": "Manutencao", "N3": "Manutencao Corretiva", "N4": "Reparo de Motor"},
        {"N1": "Servicos", "N2": "Manutencao", "N3": "Manutencao Corretiva", "N4": "Reparo de Bomba"},
        {"N1": "Servicos", "N2": "Engenharia", "N3": "Projetos", "N4": "Projeto Naval"},
        {"N1": "Servicos", "N2": "Engenharia", "N3": "Projetos", "N4": "Projeto Estrutural"},
        # --- Equipamentos ---
        {"N1": "Equipamentos", "N2": "Propulsao", "N3": "Motores Principais", "N4": "Motor Diesel Maritimo"},
        {"N1": "Equipamentos", "N2": "Propulsao", "N3": "Motores Principais", "N4": "Motor a Gas"},
        {"N1": "Equipamentos", "N2": "Propulsao", "N3": "Sistemas Auxiliares", "N4": "Bomba de Combustivel"},
        {"N1": "Equipamentos", "N2": "Propulsao", "N3": "Sistemas Auxiliares", "N4": "Trocador de Calor"},
        {"N1": "Equipamentos", "N2": "Navegacao", "N3": "Instrumentos", "N4": "Radar Maritimo"},
        {"N1": "Equipamentos", "N2": "Navegacao", "N3": "Instrumentos", "N4": "GPS Diferencial"},
    ]
    return hierarchy


@pytest.fixture
def sample_kb_entries():
    """Returns a list of 5 realistic KB entry dicts for a naval/procurement project."""
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": str(uuid.uuid4()),
            "description": "PARAFUSO SEXTAVADO M12x50 INOX A4",
            "description_norm": "parafuso sextavado m12x50 inox a4",
            "N1": "Materiais",
            "N2": "Componentes Mecanicos",
            "N3": "Fixacao",
            "N4": "Parafusos",
            "source": "llm_approved",
            "confidence": 0.92,
            "version": "v1",
            "date_added": now,
        },
        {
            "id": str(uuid.uuid4()),
            "description": "Servico de manutencao preventiva no motor principal",
            "description_norm": "servico manutencao preventiva motor principal",
            "N1": "Servicos",
            "N2": "Manutencao",
            "N3": "Manutencao Preventiva",
            "N4": "Inspecao Programada",
            "source": "consultant_correction",
            "confidence": 1.0,
            "version": "v1",
            "date_added": now,
        },
        {
            "id": str(uuid.uuid4()),
            "description": "Cabo de forca 3x16mm2 blindado naval",
            "description_norm": "cabo forca 3x16mm2 blindado naval",
            "N1": "Materiais",
            "N2": "Componentes Eletricos",
            "N3": "Cabos e Condutores",
            "N4": "Cabos de Potencia",
            "source": "llm_approved",
            "confidence": 0.88,
            "version": "v1",
            "date_added": now,
        },
        {
            "id": str(uuid.uuid4()),
            "description": "Motor diesel maritimo Wartsila 6L20",
            "description_norm": "motor diesel maritimo wartsila 6l20",
            "N1": "Equipamentos",
            "N2": "Propulsao",
            "N3": "Motores Principais",
            "N4": "Motor Diesel Maritimo",
            "source": "reclassified_with_guidance",
            "confidence": 0.95,
            "version": "v2",
            "date_added": now,
        },
        {
            "id": str(uuid.uuid4()),
            "description": "Anel O-Ring Viton 25x3mm para valvula",
            "description_norm": "anel o ring viton 25x3mm valvula",
            "N1": "Materiais",
            "N2": "Componentes Mecanicos",
            "N3": "Vedacao",
            "N4": "Aneis O-Ring",
            "source": "llm_approved",
            "confidence": 0.90,
            "version": "v1",
            "date_added": now,
        },
    ]
