---
name: revise
description: При новых данных: обнови строку claims
---
# Навык revise

При новых данных: обнови строку claims.csv (старую пометь retracted, не удаляй), выполни python tools/sfp.py impact <slug> <id>, пересчитай затронутые выводы, запиши в decisions/decision-log.md что изменилось и почему

После выполнения: обнови state.json и выполни `python tools/sfp.py log <slug> <step> "<итог>" --tokens N --minutes M`.
