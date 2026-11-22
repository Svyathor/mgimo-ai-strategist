---
name: collect
description: Сбор материалов: документы (PDF/DOCX), таблицы (CSV/XLSX через pandas или чтение), сайты из разрешённых источников
---
# Навык collect

Сбор материалов: документы (PDF/DOCX), таблицы (CSV/XLSX через pandas или чтение), сайты из разрешённых источников. Каждое сведение → строка claims.csv с источником. Список источников → evidence/sources.md

После выполнения: обнови state.json и выполни `python tools/sfp.py log <slug> <step> "<итог>" --tokens N --minutes M`.
