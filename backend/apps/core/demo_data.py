"""In-memory demo content for the presentation layer.

The frontend prototype is intentionally decoupled from the persistence layer:
these dictionaries provide realistic content for the templates until the real
services and models are connected. Nothing in this module writes to the
database, so the views stay free of business logic.
"""

from __future__ import annotations

from datetime import date
from typing import Any

SPANISH_MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

SPANISH_DAYS = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)


def today_label() -> str:
    """Return today's date formatted in Spanish."""
    today = date.today()
    return (
        f"{SPANISH_DAYS[today.weekday()]}, {today.day} de "
        f"{SPANISH_MONTHS[today.month - 1]} de {today.year}"
    )


STATS = [
    {"value": "1 248", "label": "Publicaciones indexadas", "icon": "book"},
    {"value": "18", "label": "Áreas de conocimiento", "icon": "grid"},
    {"value": "3 600", "label": "Autores registrados", "icon": "users"},
    {"value": "96 %", "label": "Revisiones a tiempo", "icon": "check-circle"},
]

RESEARCH_AREAS = [
    {
        "name": "Ciencias Computacionales",
        "count": 286,
        "icon": "cpu",
        "description": "Inteligencia artificial, software y ciencia de datos.",
    },
    {
        "name": "Energía y Recursos Naturales",
        "count": 214,
        "icon": "leaf",
        "description": "Energías renovables, ambiente y sostenibilidad.",
    },
    {
        "name": "Ciencias Agropecuarias",
        "count": 198,
        "icon": "sprout",
        "description": "Producción agrícola, suelos y biotecnología.",
    },
    {
        "name": "Salud y Bienestar",
        "count": 176,
        "icon": "heart",
        "description": "Salud pública, epidemiología y bienestar social.",
    },
    {
        "name": "Ingeniería y Tecnología",
        "count": 232,
        "icon": "settings",
        "description": "Procesos industriales, materiales y automatización.",
    },
    {
        "name": "Ciencias Sociales y Educación",
        "count": 142,
        "icon": "users",
        "description": "Sociedad, cultura, pedagogía y políticas públicas.",
    },
]

FEATURES = [
    {
        "title": "Trazabilidad de punta a punta",
        "description": (
            "Cada manuscrito conserva su historial completo: envíos, versiones, "
            "observaciones y decisiones editoriales."
        ),
        "icon": "route",
    },
    {
        "title": "Revisión a doble ciego",
        "description": (
            "Revisores y autores permanecen anónimos durante la evaluación, "
            "garantizando imparcialidad en cada dictamen."
        ),
        "icon": "shield",
    },
    {
        "title": "Versionado inmutable",
        "description": (
            "Las nuevas entregas nunca sobrescriben las anteriores. La versión "
            "vigente y su historial conviven con total claridad."
        ),
        "icon": "layers",
    },
    {
        "title": "Catálogo abierto",
        "description": (
            "La producción científica de la UNL se organiza por área, palabras "
            "clave, año e idioma para facilitar su consulta."
        ),
        "icon": "search",
    },
    {
        "title": "Auditoría confiable",
        "description": (
            "Las acciones críticas quedan registradas en una bitácora inmutable, "
            "accesible para el equipo administrador."
        ),
        "icon": "lock",
    },
    {
        "title": "Acceso institucional",
        "description": (
            "Roles de autor, revisor, editor y administrador con permisos claros "
            "y un único flujo de trabajo compartido."
        ),
        "icon": "users",
    },
]

WORKFLOW_STEPS = [
    {
        "number": "01",
        "title": "Envío del manuscrito",
        "description": (
            "El autor registra metadatos, coautores y el PDF de la versión vigente."
        ),
        "icon": "upload",
    },
    {
        "number": "02",
        "title": "Revisión doble ciego",
        "description": (
            "El editor asigna especialistas que evalúan sin conocer la identidad "
            "del autor."
        ),
        "icon": "shield",
    },
    {
        "number": "03",
        "title": "Decisión editorial",
        "description": (
            "Con las evaluaciones reunidas, el comité emite el veredicto y las "
            "observaciones."
        ),
        "icon": "scale",
    },
    {
        "number": "04",
        "title": "Publicación y difusión",
        "description": (
            "El artículo aprobado se incorpora al catálogo institucional y queda "
            "disponible para consulta."
        ),
        "icon": "book",
    },
]

FAQ = [
    {
        "question": "¿Quién puede enviar un manuscrito?",
        "answer": (
            "Docentes, investigadores y estudiantes de la Universidad Nacional de "
            "Loja con una cuenta institucional habilitada. El autor principal es "
            "quien gestiona el envío y las versiones posteriores."
        ),
    },
    {
        "question": "¿Cómo funciona la revisión a doble ciego?",
        "answer": (
            "El revisor recibe únicamente los datos académicos del manuscrito, sin "
            "nombres, filiaciones ni correos de los autores. Del mismo modo, el "
            "autor no conoce la identidad de quien evalúa."
        ),
    },
    {
        "question": "¿Puedo corregir mi manuscrito después de enviarlo?",
        "answer": (
            "Sí. Cuando el editor solicita correcciones, el autor puede cargar una "
            "nueva versión en PDF. Todas las versiones anteriores se conservan de "
            "forma permanente."
        ),
    },
    {
        "question": "¿Qué ocurre después de la decisión editorial?",
        "answer": (
            "Si el manuscrito es aceptado, pasa al catálogo institucional. Si "
            "requiere correcciones, vuelve al autor con las observaciones. Si es "
            "rechazado, se conserva el historial del proceso."
        ),
    },
    {
        "question": "¿El catálogo es de acceso público?",
        "answer": (
            "La consulta del catálogo está abierta a la comunidad universitaria. "
            "Las funciones de envío, revisión y gestión editorial requieren iniciar "
            "sesión con credenciales institucionales."
        ),
    },
]

ARTICLES: list[dict[str, Any]] = [
    {
        "slug": "riego-inteligente-sensores-iot",
        "title": (
            "Riego inteligente en cultivos andinos mediante sensores IoT y "
            "aprendizaje automático"
        ),
        "authors": [
            {"name": "María Fernanda Ortega", "affiliation": "UNL · Computación"},
            {"name": "Luis Andrade", "affiliation": "UNL · Agropecuaria"},
            {"name": "Camila Reyes", "affiliation": "UNL · Computación"},
        ],
        "authors_display": "María Fernanda Ortega, Luis Andrade y Camila Reyes",
        "area": "Ciencias Computacionales",
        "area_code": "COMP",
        "published_at": "12 sep 2026",
        "iso_date": "2026-09-12",
        "year": "2026",
        "language": "Español",
        "keywords": ["IoT", "riego", "machine learning", "agricultura"],
        "abstract": (
            "El presente estudio evalúa un sistema de riego adaptativo para cultivos "
            "andinos basado en una red de sensores de humedad y un modelo de "
            "aprendizaje supervisado. Los resultados muestran una reducción del 27 % "
            "en el consumo de agua sin afectar el rendimiento del cultivo, lo que "
            "sugiere una alternativa viable para pequeñas unidades productivas."
        ),
        "doi": "10.56789/unl.2026.0142",
        "issn": "2588-1234",
        "volume": "12",
        "issue": "3",
        "pages": "45-62",
        "featured": True,
        "accent": "blue",
    },
    {
        "slug": "microplasticos-cuenca-rio-catamayo",
        "title": (
            "Presencia de microplásticos en la cuenca del río Catamayo: "
            "caracterización y riesgo ecológico"
        ),
        "authors": [
            {"name": "Jorge Medina", "affiliation": "UNL · Recursos Naturales"},
            {"name": "Paula Cevallos", "affiliation": "UNL · Recursos Naturales"},
        ],
        "authors_display": "Jorge Medina y Paula Cevallos",
        "area": "Energía y Recursos Naturales",
        "area_code": "RRNN",
        "published_at": "28 ago 2026",
        "iso_date": "2026-08-28",
        "year": "2026",
        "language": "Español",
        "keywords": ["microplásticos", "calidad de agua", "Catamayo"],
        "abstract": (
            "Se analizaron doce puntos de muestreo a lo largo de la cuenca del río "
            "Catamayo para cuantificar la presencia de microplásticos. Los "
            "resultados evidencian concentraciones superiores a las reportadas en "
            "otras cuencas andinas y permiten identificar las principales fuentes "
            "de contaminación urbana."
        ),
        "doi": "10.56789/unl.2026.0138",
        "issn": "2588-1234",
        "volume": "12",
        "issue": "2",
        "pages": "18-36",
        "featured": True,
        "accent": "green",
    },
    {
        "slug": "abandono-academico-modelo-predictivo",
        "title": (
            "Modelo predictivo de abandono académico en programas de ingeniería "
            "de la UNL"
        ),
        "authors": [
            {"name": "Andrea Salazar", "affiliation": "UNL · Educación"},
            {"name": "Diego Pardo", "affiliation": "UNL · Computación"},
            {"name": "Rosa Jiménez", "affiliation": "UNL · Educación"},
        ],
        "authors_display": "Andrea Salazar, Diego Pardo y Rosa Jiménez",
        "area": "Ciencias Sociales y Educación",
        "area_code": "SOC",
        "published_at": "05 ago 2026",
        "iso_date": "2026-08-05",
        "year": "2026",
        "language": "Español",
        "keywords": ["abandono", "educación superior", "predicción"],
        "abstract": (
            "A partir de registros académicos anonimizados de tres cohortes, se "
            "construyó un modelo de clasificación para identificar estudiantes en "
            "riesgo de abandono. La herramienta permite priorizar acompañamiento "
            "tutorial con una precisión del 84 % en la muestra de validación."
        ),
        "doi": "10.56789/unl.2026.0129",
        "issn": "2588-1234",
        "volume": "12",
        "issue": "1",
        "pages": "71-89",
        "featured": True,
        "accent": "gold",
    },
    {
        "slug": "energia-solar-comunidades-rurales",
        "title": (
            "Electrificación rural con energía solar fotovoltaica en comunidades "
            "de la sierra sur ecuatoriana"
        ),
        "authors": [
            {"name": "Patricio Guaman", "affiliation": "UNL · Energía"},
            {"name": "Elena Torres", "affiliation": "UNL · Energía"},
        ],
        "authors_display": "Patricio Guaman y Elena Torres",
        "area": "Energía y Recursos Naturales",
        "area_code": "RRNN",
        "published_at": "22 jul 2026",
        "iso_date": "2026-07-22",
        "year": "2026",
        "language": "Español",
        "keywords": ["energía solar", "electrificación", "sostenibilidad"],
        "abstract": (
            "El trabajo documenta la implementación de microrredes solares en cuatro "
            "comunidades rurales. Se reportan indicadores de cobertura, costos "
            "nivelados y percepción de las familias beneficiarias tras dieciocho "
            "meses de operación."
        ),
        "doi": "10.56789/unl.2026.0117",
        "issn": "2588-1234",
        "volume": "11",
        "issue": "4",
        "pages": "102-119",
        "featured": False,
        "accent": "gold",
    },
    {
        "slug": "biopeliculas-empacado-alimentos",
        "title": (
            "Biopelículas a base de almidón de papa para el empacado de alimentos "
            "frescos"
        ),
        "authors": [
            {"name": "Sofía Ludeña", "affiliation": "UNL · Agroindustria"},
            {"name": "Marco Vélez", "affiliation": "UNL · Agroindustria"},
        ],
        "authors_display": "Sofía Ludeña y Marco Vélez",
        "area": "Ciencias Agropecuarias",
        "area_code": "AGRO",
        "published_at": "14 jul 2026",
        "iso_date": "2026-07-14",
        "year": "2026",
        "language": "Español",
        "keywords": ["biopolímeros", "empacado", "papa"],
        "abstract": (
            "Se desarrollaron biopelículas comestibles a partir de almidón nativo de "
            "papa y glicerol como plastificante. Las pruebas de permeabilidad y "
            "resistencia mecánica evidencian un desempeño comparable al de films "
            "comerciales de baja densidad."
        ),
        "doi": "10.56789/unl.2026.0108",
        "issn": "2588-1234",
        "volume": "11",
        "issue": "3",
        "pages": "54-70",
        "featured": False,
        "accent": "green",
    },
    {
        "slug": "salud-mental-universitarios",
        "title": (
            "Salud mental en estudiantes universitarios: prevalencia de ansiedad y "
            "factores asociados"
        ),
        "authors": [
            {"name": "Carolina Espinosa", "affiliation": "UNL · Salud"},
            {"name": "Andrés Morocho", "affiliation": "UNL · Salud"},
        ],
        "authors_display": "Carolina Espinosa y Andrés Morocho",
        "area": "Salud y Bienestar",
        "area_code": "SALUD",
        "published_at": "30 jun 2026",
        "iso_date": "2026-06-30",
        "year": "2026",
        "language": "Español",
        "keywords": ["ansiedad", "salud mental", "universidad"],
        "abstract": (
            "Estudio transversal aplicado a 842 estudiantes de la UNL. La prevalencia "
            "de ansiedad moderada a severa alcanzó el 31,4 %, con una relación "
            "significativa entre carga académica, horas de sueño y apoyo social "
            "percibido."
        ),
        "doi": "10.56789/unl.2026.0097",
        "issn": "2588-1234",
        "volume": "11",
        "issue": "2",
        "pages": "12-29",
        "featured": False,
        "accent": "blue",
    },
    {
        "slug": "gemelos-digitales-procesos-industriales",
        "title": (
            "Gemelos digitales para la optimización de procesos industriales: una "
            "revisión sistemática"
        ),
        "authors": [
            {"name": "Ricardo Paladines", "affiliation": "UNL · Mecánica"},
            {"name": "Natalia Córdova", "affiliation": "UNL · Computación"},
        ],
        "authors_display": "Ricardo Paladines y Natalia Córdova",
        "area": "Ingeniería y Tecnología",
        "area_code": "ING",
        "published_at": "18 jun 2026",
        "iso_date": "2026-06-18",
        "year": "2026",
        "language": "Inglés",
        "keywords": ["digital twin", "industry 4.0", "optimization"],
        "abstract": (
            "La revisión analiza 64 publicaciones sobre gemelos digitales en procesos "
            "de manufactura. Se identifican arquitecturas de referencia, métricas de "
            "desempeño y brechas de implementación en contextos de industria "
            "emergente."
        ),
        "doi": "10.56789/unl.2026.0085",
        "issn": "2588-1234",
        "volume": "11",
        "issue": "1",
        "pages": "88-106",
        "featured": False,
        "accent": "blue",
    },
    {
        "slug": "patrimonio-arquitectonico-loja",
        "title": (
            "Valoración del patrimonio arquitectónico de Loja mediante narrativas "
            "digitales"
        ),
        "authors": [
            {"name": "Verónica Aguirre", "affiliation": "UNL · Arquitectura"},
            {"name": "Fabián Rojas", "affiliation": "UNL · Comunicación"},
        ],
        "authors_display": "Verónica Aguirre y Fabián Rojas",
        "area": "Ciencias Sociales y Educación",
        "area_code": "SOC",
        "published_at": "02 jun 2026",
        "iso_date": "2026-06-02",
        "year": "2026",
        "language": "Español",
        "keywords": ["patrimonio", "narrativas digitales", "Loja"],
        "abstract": (
            "El proyecto articula recorridos patrimoniales con contenidos digitales "
            "accesibles desde dispositivos móviles. La evaluación de usabilidad con "
            "visitantes y residentes muestra una mejora significativa en la "
            "comprensión del valor histórico del centro urbano."
        ),
        "doi": "10.56789/unl.2026.0079",
        "issn": "2588-1234",
        "volume": "10",
        "issue": "4",
        "pages": "34-51",
        "featured": False,
        "accent": "gold",
    },
    {
        "slug": "hongos-micorrizicos-suelos-andinos",
        "title": (
            "Hongos micorrízicos arbusculares como indicadores de salud del suelo "
            "en sistemas agroforestales andinos"
        ),
        "authors": [
            {"name": "Gabriela Suárez", "affiliation": "UNL · Biología"},
            {"name": "Hugo Castillo", "affiliation": "UNL · Agropecuaria"},
            {"name": "Inés Villamagua", "affiliation": "UNL · Biología"},
        ],
        "authors_display": "Gabriela Suárez, Hugo Castillo e Inés Villamagua",
        "area": "Ciencias Agropecuarias",
        "area_code": "AGRO",
        "published_at": "20 may 2026",
        "iso_date": "2026-05-20",
        "year": "2026",
        "language": "Español",
        "keywords": ["micorrizas", "suelo", "agroforestería"],
        "abstract": (
            "Se comparó la colonización micorrízica en parcelas con distintos usos "
            "del suelo. Los sistemas agroforestales presentaron una mayor diversidad "
            "de morfotipos y una correlación positiva con el contenido de materia "
            "orgánica."
        ),
        "doi": "10.56789/unl.2026.0064",
        "issn": "2588-1234",
        "volume": "10",
        "issue": "3",
        "pages": "60-77",
        "featured": False,
        "accent": "green",
    },
]

MANUSCRIPTS: list[dict[str, Any]] = [
    {
        "id": 1,
        "code": "MAN-2026-0184",
        "title": (
            "Análisis de sentimiento en redes sociales durante emergencias "
            "climáticas en la región sur del Ecuador"
        ),
        "authors": ["Ana Autora", "Diego Pardo"],
        "authors_display": "Ana Autora y Diego Pardo",
        "area": "Ciencias Computacionales",
        "category": "Procesamiento de lenguaje natural",
        "status": "under_review",
        "status_label": "En revisión",
        "status_class": "status--review",
        "submitted_at": "18 sep 2026",
        "updated_at": "Hace 2 días",
        "version": 2,
        "language": "Español",
        "keywords": ["sentimiento", "redes sociales", "emergencias"],
        "doi": "10.56789/unl.2026.0184",
        "issn": "2588-1234",
        "funding": "Proyecto de investigación UNL 2025-014",
        "abstract": (
            "La investigación propone un pipeline de análisis de sentimiento para "
            "monitorear la respuesta ciudadana durante eventos climáticos extremos. "
            "Se evaluaron más de 48 000 publicaciones provenientes de tres provincias "
            "del sur del país."
        ),
        "observations": (
            "La editora solicitó ampliar la descripción del corpus y justificar la "
            "selección de las ventanas temporales."
        ),
        "versions": [
            {
                "number": 2,
                "date": "12 oct 2026",
                "notes": "Se amplió el corpus y se añadió el análisis temporal.",
                "size": "1,8 MB",
                "current": True,
            },
            {
                "number": 1,
                "date": "18 sep 2026",
                "notes": "Versión inicial enviada para revisión.",
                "size": "1,4 MB",
                "current": False,
            },
        ],
        "reviewers": [
            {"name": "Raúl Revisor", "initials": "RR", "status": "Completada"},
            {"name": "Marta Espinoza", "initials": "ME", "status": "En proceso"},
        ],
        "verdict": None,
        "timeline": [
            {
                "date": "12 oct 2026",
                "title": "Nueva versión cargada",
                "description": "El autor cargó la versión v2 del manuscrito.",
                "tone": "info",
            },
            {
                "date": "02 oct 2026",
                "title": "Revisores asignados",
                "description": "Se asignaron dos especialistas al manuscrito.",
                "tone": "info",
            },
            {
                "date": "18 sep 2026",
                "title": "Manuscrito recibido",
                "description": "Envío registrado y habilitado para revisión.",
                "tone": "success",
            },
        ],
        "editable": False,
        "can_accept_version": False,
    },
    {
        "id": 2,
        "code": "MAN-2026-0179",
        "title": (
            "Modelo de optimización multiobjetivo para la distribución de ayuda "
            "humanitaria en zonas rurales"
        ),
        "authors": ["Ana Autora", "Camila Reyes"],
        "authors_display": "Ana Autora y Camila Reyes",
        "area": "Ingeniería y Tecnología",
        "category": "Investigación de operaciones",
        "status": "requires_changes",
        "status_label": "Requiere correcciones",
        "status_class": "status--changes",
        "submitted_at": "05 sep 2026",
        "updated_at": "Hace 5 días",
        "version": 1,
        "language": "Español",
        "keywords": ["logística", "optimización", "ayuda humanitaria"],
        "doi": "10.56789/unl.2026.0179",
        "issn": "2588-1234",
        "funding": "Sin financiamiento externo",
        "abstract": (
            "Se formula un modelo multiobjetivo para planificar rutas de distribución "
            "de ayuda humanitaria considerando tiempo de respuesta, costo y equidad "
            "territorial. La validación se realizó con datos de la emergencia "
            "invernal de 2025."
        ),
        "observations": (
            "El comité solicita incorporar un análisis de sensibilidad de los pesos "
            "del modelo y precisar la fuente de los datos de demanda."
        ),
        "versions": [
            {
                "number": 1,
                "date": "05 sep 2026",
                "notes": "Versión inicial enviada para revisión.",
                "size": "2,1 MB",
                "current": True,
            }
        ],
        "reviewers": [
            {"name": "Raúl Revisor", "initials": "RR", "status": "Completada"},
        ],
        "verdict": {
            "decision": "Requiere correcciones",
            "date": "16 oct 2026",
            "observations": (
                "Se solicita ampliar el análisis de sensibilidad y documentar los "
                "supuestos del modelo antes de una nueva evaluación."
            ),
        },
        "timeline": [
            {
                "date": "16 oct 2026",
                "title": "Veredicto: requiere correcciones",
                "description": "La editora emitió observaciones para el autor.",
                "tone": "warning",
            },
            {
                "date": "28 sep 2026",
                "title": "Evaluación recibida",
                "description": "El revisor recomendó cambios mayores.",
                "tone": "info",
            },
            {
                "date": "05 sep 2026",
                "title": "Manuscrito recibido",
                "description": "Envío registrado y habilitado para revisión.",
                "tone": "success",
            },
        ],
        "editable": True,
        "can_accept_version": True,
    },
    {
        "id": 3,
        "code": "MAN-2026-0168",
        "title": (
            "Visualización interactiva de datos abiertos para la gestión municipal "
            "de Loja"
        ),
        "authors": ["Ana Autora"],
        "authors_display": "Ana Autora",
        "area": "Ciencias Computacionales",
        "category": "Visualización de datos",
        "status": "draft",
        "status_label": "Borrador",
        "status_class": "status--draft",
        "submitted_at": "Sin enviar",
        "updated_at": "Ayer",
        "version": 0,
        "language": "Español",
        "keywords": ["datos abiertos", "visualización", "gobierno local"],
        "doi": "",
        "issn": "2588-1234",
        "funding": "Proyecto de vinculación UNL",
        "abstract": (
            "Propuesta de un tablero público para explorar datos abiertos del "
            "municipio de Loja. El manuscrito se encuentra en preparación y aún no "
            "ha sido enviado al comité editorial."
        ),
        "observations": "",
        "versions": [],
        "reviewers": [],
        "verdict": None,
        "timeline": [
            {
                "date": "20 oct 2026",
                "title": "Borrador actualizado",
                "description": "Se completaron los metadatos del manuscrito.",
                "tone": "info",
            }
        ],
        "editable": True,
        "can_accept_version": False,
    },
    {
        "id": 4,
        "code": "MAN-2026-0152",
        "title": (
            "Evaluación de la calidad del aire en el centro histórico de Loja "
            "mediante sensores de bajo costo"
        ),
        "authors": ["Ana Autora", "Jorge Medina"],
        "authors_display": "Ana Autora y Jorge Medina",
        "area": "Energía y Recursos Naturales",
        "category": "Calidad ambiental",
        "status": "published",
        "status_label": "Publicado",
        "status_class": "status--published",
        "submitted_at": "22 jul 2026",
        "updated_at": "Hace 3 semanas",
        "version": 3,
        "language": "Español",
        "keywords": ["calidad del aire", "sensores", "Loja"],
        "doi": "10.56789/unl.2026.0152",
        "issn": "2588-1234",
        "funding": "Cooperación internacional",
        "abstract": (
            "Se desplegó una red de diez sensores de bajo costo para monitorear "
            "material particulado en el centro histórico. Los resultados permiten "
            "identificar patrones horarios y zonas prioritarias para intervención."
        ),
        "observations": "",
        "versions": [
            {
                "number": 3,
                "date": "14 sep 2026",
                "notes": "Versión aceptada para publicación.",
                "size": "1,9 MB",
                "current": True,
            },
            {
                "number": 2,
                "date": "30 ago 2026",
                "notes": "Se incorporaron observaciones del comité.",
                "size": "1,7 MB",
                "current": False,
            },
            {
                "number": 1,
                "date": "22 jul 2026",
                "notes": "Versión inicial enviada para revisión.",
                "size": "1,6 MB",
                "current": False,
            },
        ],
        "reviewers": [
            {"name": "Marta Espinoza", "initials": "ME", "status": "Completada"},
            {"name": "Raúl Revisor", "initials": "RR", "status": "Completada"},
        ],
        "verdict": {
            "decision": "Aceptado",
            "date": "10 sep 2026",
            "observations": (
                "El comité editorial aprueba la publicación de la versión v3 en el "
                "catálogo institucional."
            ),
        },
        "timeline": [
            {
                "date": "14 sep 2026",
                "title": "Publicado en el catálogo",
                "description": "El artículo quedó disponible para consulta pública.",
                "tone": "success",
            },
            {
                "date": "10 sep 2026",
                "title": "Veredicto: aceptado",
                "description": "El comité aprobó la publicación del manuscrito.",
                "tone": "success",
            },
            {
                "date": "22 jul 2026",
                "title": "Manuscrito recibido",
                "description": "Envío registrado y habilitado para revisión.",
                "tone": "info",
            },
        ],
        "editable": False,
        "can_accept_version": False,
    },
    {
        "id": 5,
        "code": "MAN-2026-0147",
        "title": (
            "Aprendizaje basado en proyectos para el desarrollo de competencias "
            "digitales docentes"
        ),
        "authors": ["Ana Autora", "Andrea Salazar"],
        "authors_display": "Ana Autora y Andrea Salazar",
        "area": "Ciencias Sociales y Educación",
        "category": "Innovación educativa",
        "status": "accepted",
        "status_label": "Aceptado",
        "status_class": "status--accepted",
        "submitted_at": "14 jul 2026",
        "updated_at": "Hace 1 mes",
        "version": 2,
        "language": "Español",
        "keywords": ["educación", "competencias digitales", "ABP"],
        "doi": "10.56789/unl.2026.0147",
        "issn": "2588-1234",
        "funding": "Proyecto de innovación docente",
        "abstract": (
            "La experiencia analiza la implementación del aprendizaje basado en "
            "proyectos en dos cohortes de docentes de educación básica. Se reportan "
            "avances en la planificación de actividades mediadas por tecnología."
        ),
        "observations": "",
        "versions": [
            {
                "number": 2,
                "date": "01 sep 2026",
                "notes": "Versión final con ajustes de formato.",
                "size": "1,2 MB",
                "current": True,
            },
            {
                "number": 1,
                "date": "14 jul 2026",
                "notes": "Versión inicial enviada para revisión.",
                "size": "1,1 MB",
                "current": False,
            },
        ],
        "reviewers": [
            {"name": "Marta Espinoza", "initials": "ME", "status": "Completada"},
        ],
        "verdict": {
            "decision": "Aceptado",
            "date": "28 ago 2026",
            "observations": "Aprobado para publicación.",
        },
        "timeline": [
            {
                "date": "28 ago 2026",
                "title": "Veredicto: aceptado",
                "description": "El comité aprobó la publicación del manuscrito.",
                "tone": "success",
            },
            {
                "date": "14 jul 2026",
                "title": "Manuscrito recibido",
                "description": "Envío registrado y habilitado para revisión.",
                "tone": "info",
            },
        ],
        "editable": False,
        "can_accept_version": False,
    },
]

REVIEWS: list[dict[str, Any]] = [
    {
        "id": 1,
        "code": "REV-2026-0321",
        "manuscript_code": "MAN-2026-0192",
        "title": (
            "Modelos de lenguaje para la clasificación automática de documentos "
            "académicos"
        ),
        "area": "Ciencias Computacionales",
        "version": 2,
        "status": "pending",
        "status_label": "Pendiente",
        "status_class": "status--draft",
        "due_date": "28 oct 2026",
        "assigned_at": "16 oct 2026",
        "language": "Español",
        "keywords": ["LLM", "clasificación", "documentos"],
        "abstract": (
            "El manuscrito compara tres arquitecturas de modelos de lenguaje para la "
            "clasificación de documentos académicos según su área de conocimiento. "
            "Se reportan métricas de precisión, exhaustividad y tiempo de inferencia."
        ),
        "pages": "24",
        "pdf_size": "1,6 MB",
        "reviewer_notes": "",
    },
    {
        "id": 2,
        "code": "REV-2026-0318",
        "manuscript_code": "MAN-2026-0188",
        "title": (
            "Redes neuronales para la detección temprana de enfermedades en cultivos "
            "de cacao"
        ),
        "area": "Ciencias Agropecuarias",
        "version": 1,
        "status": "in_progress",
        "status_label": "En proceso",
        "status_class": "status--review",
        "due_date": "30 oct 2026",
        "assigned_at": "12 oct 2026",
        "language": "Español",
        "keywords": ["redes neuronales", "cacao", "fitopatología"],
        "abstract": (
            "Se propone un sistema de visión artificial para identificar lesiones "
            "foliares en plantaciones de cacao. El conjunto de datos incluye imágenes "
            "de campo capturadas durante dos ciclos productivos."
        ),
        "pages": "31",
        "pdf_size": "2,4 MB",
        "reviewer_notes": "",
    },
    {
        "id": 3,
        "code": "REV-2026-0307",
        "manuscript_code": "MAN-2026-0175",
        "title": (
            "Análisis de la movilidad urbana sostenible en ciudades intermedias del "
            "Ecuador"
        ),
        "area": "Ingeniería y Tecnología",
        "version": 1,
        "status": "completed",
        "status_label": "Completada",
        "status_class": "status--published",
        "due_date": "10 oct 2026",
        "assigned_at": "22 sep 2026",
        "language": "Español",
        "keywords": ["movilidad", "sostenibilidad", "ciudades"],
        "abstract": (
            "La investigación examina patrones de movilidad y accesibilidad en cuatro "
            "ciudades intermedias. Se combinan encuestas de origen-destino con datos "
            "abiertos de transporte público."
        ),
        "pages": "28",
        "pdf_size": "1,9 MB",
        "reviewer_notes": (
            "Se recomienda aceptar con cambios menores. La metodología es sólida y la "
            "discusión aporta evidencia útil para la planificación local."
        ),
    },
    {
        "id": 4,
        "code": "REV-2026-0299",
        "manuscript_code": "MAN-2026-0169",
        "title": (
            "Estrategias de conservación de bosques secos en la provincia de Loja"
        ),
        "area": "Energía y Recursos Naturales",
        "version": 1,
        "status": "completed",
        "status_label": "Completada",
        "status_class": "status--published",
        "due_date": "02 oct 2026",
        "assigned_at": "15 sep 2026",
        "language": "Español",
        "keywords": ["bosque seco", "conservación", "biodiversidad"],
        "abstract": (
            "Se evalúan estrategias comunitarias de conservación en tres sectores de "
            "bosque seco. El estudio documenta indicadores de cobertura vegetal y "
            "participación local."
        ),
        "pages": "19",
        "pdf_size": "1,1 MB",
        "reviewer_notes": "Trabajo pertinente; se recomiendan cambios menores.",
    },
]

REVIEWERS = [
    {
        "name": "Raúl Revisor",
        "initials": "RR",
        "area": "Ciencias Computacionales",
        "workload": 2,
        "status": "Disponible",
    },
    {
        "name": "Marta Espinoza",
        "initials": "ME",
        "area": "Ciencias Sociales y Educación",
        "workload": 1,
        "status": "Disponible",
    },
    {
        "name": "Hugo Castillo",
        "initials": "HC",
        "area": "Ciencias Agropecuarias",
        "workload": 3,
        "status": "Ocupado",
    },
    {
        "name": "Natalia Córdova",
        "initials": "NC",
        "area": "Ingeniería y Tecnología",
        "workload": 0,
        "status": "Disponible",
    },
    {
        "name": "Carolina Espinosa",
        "initials": "CE",
        "area": "Salud y Bienestar",
        "workload": 1,
        "status": "Disponible",
    },
]

AUDIT_EVENTS = [
    {
        "timestamp": "21 oct 2026 · 09:42",
        "actor": "Elena Editora",
        "role": "Editor",
        "action": "verdict.issued",
        "action_label": "Veredicto emitido",
        "entity": "Manuscrito",
        "entity_id": "MAN-2026-0179",
        "description": "Se emitió el veredicto «Requiere correcciones».",
        "ip": "192.168.10.24",
        "tone": "warning",
    },
    {
        "timestamp": "21 oct 2026 · 09:15",
        "actor": "Ana Autora",
        "role": "Autor",
        "action": "version.uploaded",
        "action_label": "Versión cargada",
        "entity": "Manuscrito",
        "entity_id": "MAN-2026-0184",
        "description": "Se cargó la versión v2 del documento principal.",
        "ip": "192.168.10.18",
        "tone": "info",
    },
    {
        "timestamp": "20 oct 2026 · 17:08",
        "actor": "Raúl Revisor",
        "role": "Revisor",
        "action": "review.completed",
        "action_label": "Evaluación registrada",
        "entity": "Asignación",
        "entity_id": "REV-2026-0321",
        "description": "Evaluación enviada con recomendación de cambios menores.",
        "ip": "192.168.10.32",
        "tone": "success",
    },
    {
        "timestamp": "20 oct 2026 · 15:31",
        "actor": "Elena Editora",
        "role": "Editor",
        "action": "reviewer.assigned",
        "action_label": "Revisor asignado",
        "entity": "Manuscrito",
        "entity_id": "MAN-2026-0192",
        "description": "Se asignó a Marta Espinoza como revisora.",
        "ip": "192.168.10.24",
        "tone": "info",
    },
    {
        "timestamp": "20 oct 2026 · 11:02",
        "actor": "Administrador Institucional",
        "role": "Administrador",
        "action": "user.role_changed",
        "action_label": "Rol actualizado",
        "entity": "Usuario",
        "entity_id": "docente.unl",
        "description": "Se habilitó el rol de revisor para la cuenta docente.",
        "ip": "192.168.10.10",
        "tone": "neutral",
    },
    {
        "timestamp": "19 oct 2026 · 16:44",
        "actor": "Ana Autora",
        "role": "Autor",
        "action": "auth.login",
        "action_label": "Inicio de sesión",
        "entity": "Sesión",
        "entity_id": "S-8842",
        "description": "Acceso exitoso desde el campus universitario.",
        "ip": "192.168.10.18",
        "tone": "neutral",
    },
    {
        "timestamp": "19 oct 2026 · 14:20",
        "actor": "Elena Editora",
        "role": "Editor",
        "action": "manuscript.status_changed",
        "action_label": "Estado actualizado",
        "entity": "Manuscrito",
        "entity_id": "MAN-2026-0184",
        "description": "El manuscrito pasó de «Recibido» a «En revisión».",
        "ip": "192.168.10.24",
        "tone": "info",
    },
    {
        "timestamp": "18 oct 2026 · 10:05",
        "actor": "Administrador Institucional",
        "role": "Administrador",
        "action": "catalog.published",
        "action_label": "Artículo publicado",
        "entity": "Manuscrito",
        "entity_id": "MAN-2026-0152",
        "description": "El artículo se incorporó al catálogo institucional.",
        "ip": "192.168.10.10",
        "tone": "success",
    },
]

ACTIVITY = [
    {
        "title": "Nueva versión cargada",
        "description": "v2 de «Análisis de sentimiento en redes sociales».",
        "time": "Hace 2 horas",
        "icon": "layers",
        "tone": "info",
    },
    {
        "title": "Evaluación completada",
        "description": "Raúl Revisor envió su dictamen para MAN-2026-0184.",
        "time": "Ayer · 16:30",
        "icon": "check-circle",
        "tone": "success",
    },
    {
        "title": "Correcciones solicitadas",
        "description": "El comité dejó observaciones en MAN-2026-0179.",
        "time": "Hace 2 días",
        "icon": "alert",
        "tone": "warning",
    },
    {
        "title": "Manuscrito recibido",
        "description": "Se registró el envío MAN-2026-0192.",
        "time": "Hace 3 días",
        "icon": "file",
        "tone": "neutral",
    },
]

TASKS = [
    {
        "title": "Completar metadatos del borrador",
        "description": "Falta el DOI y la afiliación de un coautor.",
        "due": "Hoy",
        "priority": "Alta",
        "tone": "danger",
        "url_name": "publications:detail",
        "manuscript_id": 3,
    },
    {
        "title": "Cargar versión corregida",
        "description": "MAN-2026-0179 requiere una nueva versión en PDF.",
        "due": "25 oct",
        "priority": "Media",
        "tone": "warning",
        "url_name": "publications:detail",
        "manuscript_id": 2,
    },
    {
        "title": "Revisar manuscrito asignado",
        "description": "Evaluación de MAN-2026-0192 pendiente.",
        "due": "28 oct",
        "priority": "Media",
        "tone": "info",
        "url_name": "reviews:evaluate",
        "review_id": 1,
    },
]

NOTIFICATIONS = [
    {
        "title": "Evaluación recibida",
        "description": "Raúl Revisor completó la evaluación de MAN-2026-0184.",
        "time": "Hace 2 horas",
        "icon": "check-circle",
        "tone": "success",
    },
    {
        "title": "Correcciones solicitadas",
        "description": "El comité solicita ajustes en MAN-2026-0179.",
        "time": "Hace 5 días",
        "icon": "alert",
        "tone": "warning",
    },
    {
        "title": "Nueva asignación de revisión",
        "description": "Tiene un manuscrito pendiente de evaluar.",
        "time": "Hace 6 días",
        "icon": "shield",
        "tone": "info",
    },
]


def get_article(slug: str) -> dict[str, Any] | None:
    """Return a demo article by slug, or ``None`` when it does not exist."""
    return next((article for article in ARTICLES if article["slug"] == slug), None)


def get_manuscript(manuscript_id: int) -> dict[str, Any] | None:
    """Return a demo manuscript by numeric identifier."""
    return next(
        (manuscript for manuscript in MANUSCRIPTS if manuscript["id"] == manuscript_id),
        None,
    )


def get_review(review_id: int) -> dict[str, Any] | None:
    """Return a demo review assignment by numeric identifier."""
    return next((review for review in REVIEWS if review["id"] == review_id), None)


def featured_articles() -> list[dict[str, Any]]:
    """Return the articles highlighted on the landing page."""
    return [article for article in ARTICLES if article["featured"]]


def related_articles(article: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    """Return articles from the same area, excluding the current one."""
    related = [
        candidate
        for candidate in ARTICLES
        if candidate["area"] == article["area"] and candidate["slug"] != article["slug"]
    ]
    return related[:limit]
