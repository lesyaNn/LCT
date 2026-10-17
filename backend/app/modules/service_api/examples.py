"""Illustrative requests, validated against the actual route models in tests."""

UNIVERSITY_ID = "11111111-1111-4111-8111-111111111111"
PROGRAM_ID = "22222222-2222-4222-8222-222222222222"
PRODUCT_ID = "33333333-3333-4333-8333-333333333333"
DIRECTION_ID = "44444444-4444-4444-8444-444444444444"
TEMPLATE_ID = "55555555-5555-4555-8555-555555555555"
VENDOR_ID = "77777777-7777-4777-8777-777777777777"

REQUEST_EXAMPLES = {
    ("/api/v1/universities", "post"): {"name": "Тестовый университет", "city": "Москва"},
    ("/api/v1/universities/{university_id}", "patch"): {"city": "Казань"},
    ("/api/v1/directions", "post"): {
        "code": "09.03.01",
        "name": "Информатика и вычислительная техника",
    },
    ("/api/v1/programs", "post"): {
        "direction_id": DIRECTION_ID,
        "name": "Анализ данных",
        "description": "Базовый курс",
    },
    ("/api/v1/vendors", "post"): {"name": "Тестовый вендор"},
    ("/api/v1/products", "post"): {
        "vendor_id": VENDOR_ID,
        "program_id": PROGRAM_ID,
        "name": "Учебная платформа",
        "version": "1.0",
    },
    ("/api/v1/responsibles", "post"): {
        "full_name": "Тестовый сотрудник",
        "email": "employee@example.org",
    },
    ("/api/v1/universities/{university_id}/programs", "post"): {
        "program_id": PROGRAM_ID,
        "status": "planned",
    },
    ("/api/v1/contracts", "post"): {
        "university_id": UNIVERSITY_ID,
        "contract_number": "DEMO-001",
        "signed_at": "2026-10-17",
        "expires_at": "2027-10-17",
        "status_raw": "signed",
    },
    ("/api/v1/licenses", "post"): {
        "university_id": UNIVERSITY_ID,
        "product_id": PRODUCT_ID,
        "license_number": "DEMO-LIC-001",
        "signed_at": "2026-10-17",
        "expires_at": "2027-10-17",
    },
    ("/api/v1/universities/{university_id}/meetings", "post"): {
        "subject": "Обсуждение учебной программы",
        "meeting_type": "online",
        "meeting_at": "2026-10-20T10:00:00+03:00",
        "participants": [],
    },
    ("/api/v1/workflow/instances", "post"): {
        "university_id": UNIVERSITY_ID,
        "template_id": TEMPLATE_ID,
        "program_id": PROGRAM_ID,
    },
    ("/api/v1/reports", "post"): {"format": "xlsx", "filters": {}},
    ("/api/v1/integrations/lms/ingest", "post"): {
        "university_id": UNIVERSITY_ID,
        "programs": [{"program_id": PROGRAM_ID, "learners_count": 24, "flows_count": 2}],
    },
    ("/api/v1/integrations/website/ingest", "post"): {
        "university_id": UNIVERSITY_ID,
        "applications": [
            {
                "external_id": "website-demo-001",
                "program_id": PROGRAM_ID,
                "status": "new",
                "external_created_at": "2026-10-17T10:00:00Z",
            }
        ],
    },
    ("/api/v1/assistant/chat", "post"): {"message": "Как скачать отчёт?", "page": "reports"},
}
