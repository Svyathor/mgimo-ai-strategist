#!/usr/bin/env python3
"""sfp — CLI «Стратега Фабрики продуктов». Только стандартная библиотека Python 3.9+.

Команды:
  init <slug>              создать новый проект из шаблона (агент работает не только с демо)
  status [slug]            где остановились: шаг, открытые вопросы, следующий шаг (продолжение после перерыва)
  log <slug> <step> <action> [--tokens N] [--usd X] [--minutes M]   записать действие и стоимость
  cost <slug>              итог времени и расходов по журналу
  check <slug>             проверка качества: у каждого утверждения есть источник и тип
  impact <slug> <claim_id> какие выводы затронет изменение утверждения (пересмотр при новых данных)
  econ [--json]            экономика демо-проекта: сценарии, граница решения, прогноз 5 показателей
  samplesize --p0 0.12 --p1 0.09 [--icc 0.05 --m 3]   размер пилота (кластеры = семейные группы)
"""
import argparse, csv, json, math, os, shutil, sys, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
TEMPLATE = ROOT / "templates" / "project"
STEPS = ["0-intake", "1-materials", "2-research", "3-options", "4-decision", "5-strategy", "6-pilot-plan", "7-after-decision"]


def _proj(slug):
    p = PROJECTS / slug
    if not p.exists():
        sys.exit(f"[ошибка] проект '{slug}' не найден в {PROJECTS}")
    return p


def _state(p):
    f = p / "state.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def cmd_init(a):
    dst = PROJECTS / a.slug
    if dst.exists():
        sys.exit(f"[стоп] проект {a.slug} уже существует — не перезаписываю. Используйте: sfp status {a.slug}")
    shutil.copytree(TEMPLATE, dst)
    st = _state(dst)
    st.update({"project": a.slug, "created": datetime.date.today().isoformat(), "current_step": STEPS[0]})
    (dst / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Создан проект {dst}. Положите материалы в {dst/'inputs'} и скажите агенту: «начни проект {a.slug}».")


def cmd_status(a):
    slugs = [a.slug] if a.slug else sorted(d.name for d in PROJECTS.iterdir() if d.is_dir())
    for s in slugs:
        st = _state(PROJECTS / s)
        print(f"== {s} ==")
        print(f"  шаг: {st.get('current_step')}  | статус: {st.get('status','-')}")
        done = st.get("steps_done", [])
        print(f"  выполнено: {', '.join(done) if done else '—'}")
        for q in st.get("open_questions", []):
            print(f"  ? {q}")
        for h in st.get("waiting_for_human", []):
            print(f"  ⏸ ждёт решения человека: {h}")
        print(f"  следующее действие: {st.get('next_action','—')}")


def cmd_log(a):
    p = _proj(a.slug)
    f = p / "logs" / "actions.csv"
    f.parent.mkdir(exist_ok=True)
    new = not f.exists()
    with f.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["ts", "step", "action", "tokens", "usd", "minutes"])
        w.writerow([datetime.datetime.now().isoformat(timespec="seconds"), a.step, a.action, a.tokens, a.usd, a.minutes])
    print("записано")


def cmd_cost(a):
    f = _proj(a.slug) / "logs" / "actions.csv"
    if not f.exists():
        sys.exit("журнал пуст")
    rows = list(csv.DictReader(f.open(encoding="utf-8")))
    tok = sum(int(r["tokens"] or 0) for r in rows)
    usd = sum(float(r["usd"] or 0) for r in rows)
    mins = sum(float(r["minutes"] or 0) for r in rows)
    by = {}
    for r in rows:
        by.setdefault(r["step"], [0, 0.0])
        by[r["step"]][0] += int(r["tokens"] or 0)
        by[r["step"]][1] += float(r["usd"] or 0)
    print(f"Действий: {len(rows)} | токенов ≈ {tok:,} | ${usd:.2f} | время ≈ {mins:.0f} мин")
    for k, (t, u) in by.items():
        print(f"  {k:<18} {t:>9,} ток.  ${u:.2f}")


def _claims(p):
    return list(csv.DictReader((p / "evidence" / "claims.csv").open(encoding="utf-8")))


def cmd_check(a):
    p = _proj(a.slug)
    bad = 0
    for c in _claims(p):
        if c["type"] not in {"FACT", "ASSUMPTION", "HYPOTHESIS", "FORECAST", "SYNTHETIC", "DECISION"}:
            print(f"[{c['id']}] неизвестный тип {c['type']}"); bad += 1
        if c["type"] == "FACT" and not c["source"].strip():
            print(f"[{c['id']}] ФАКТ без источника"); bad += 1
        if c["type"] == "SYNTHETIC" and "не доказывает" not in c["note"]:
            print(f"[{c['id']}] синтетика без пометки «не доказывает спрос»"); bad += 1
        if c["status"] == "retracted" and c["used_in"].strip():
            print(f"[{c['id']}] отозванное утверждение всё ещё используется в {c['used_in']}"); bad += 1
    print("OK: все утверждения типизированы и имеют источники" if not bad else f"Найдено проблем: {bad}")
    sys.exit(1 if bad else 0)


def cmd_impact(a):
    p = _proj(a.slug)
    cl = {c["id"]: c for c in _claims(p)}
    if a.claim not in cl:
        sys.exit(f"нет утверждения {a.claim}")
    affected, frontier = [], [a.claim]
    while frontier:
        cur = frontier.pop()
        for c in cl.values():
            deps = [d.strip() for d in c["depends_on"].split(";") if d.strip()]
            if cur in deps and c["id"] not in affected:
                affected.append(c["id"]); frontier.append(c["id"])
    print(f"Изменилось: {a.claim} — {cl[a.claim]['statement']}")
    if not affected:
        print("Зависимых выводов нет.")
    for i in affected:
        c = cl[i]
        print(f"  → {i} [{c['type']}] {c['statement']}  (используется: {c['used_in'] or '—'})")
    docs = sorted({u.strip() for i in [a.claim] + affected for u in cl[i]["used_in"].split(";") if u.strip()})
    print("Пересмотреть разделы:", ", ".join(docs) or "—")


# ---------------- Экономика демо-проекта (бриф МегаФон, учебные числа) ----------------
FACTS = dict(gp_nochange=279.0, gp_target=285.0, rub_per_month=500, groups_start=6500, groups_nochange=8000,
             groups_target=12000, active_nochange=5000, active_target=8000, owners_nochange=1000, owners_target=2000,
             activation_nochange=0.45, activation_target=0.60)

SCEN = {  # допущения A-xx, см. evidence/claims.csv
    "low":  dict(nums_per_group=2.5, r0=0.12, r1=0.105, churn_uplift=0.010, extra_groups=500,  new_member_share=0.05, members_per_new_group=1.5, act_share=0.64, activation=0.48, calls_per_event=0.15),
    "base": dict(nums_per_group=3.0, r0=0.12, r1=0.090, churn_uplift=0.020, extra_groups=1500, new_member_share=0.10, members_per_new_group=2.0, act_share=0.67, activation=0.52, calls_per_event=0.25),
    "high": dict(nums_per_group=3.5, r0=0.12, r1=0.080, churn_uplift=0.030, extra_groups=2500, new_member_share=0.15, members_per_new_group=2.0, act_share=0.70, activation=0.56, calls_per_event=0.35),
}
CALL_COST = 120          # руб. за обращение (A-12)
DIRECT_COST_PER_ALERT = 0.3  # руб. за push/SMS (A-13)
PILOT_SHARE = 0.10       # доля групп в пилоте (Q2, мес. 4–6)
FULL_FROM = 7            # широкий запуск с июля, если решение Q2 положительное
PM_COST = 0.35           # млн руб. за человеко-месяц (A-14)
DEV_PM = 3 + 3 + 3 + 1   # разработка 3 + дизайнер 0.5×6 + аналитик 0.5×6 + тестирование 1 = 10 чел.-мес (strategy.md, ч.5)


def econ(s):
    f = FACTS
    groups_avg = (f["groups_start"] + f["groups_nochange"]) / 2
    nums = groups_avg * s["nums_per_group"]
    retained_cum, extra_months, events_avoided, alerts = 0.0, 0.0, 0.0, 0.0
    for m in range(1, 13):
        cov = 0 if m < 4 else (PILOT_SHARE if m < FULL_FROM else 1.0)
        avoided = nums * cov * (s["r0"] - s["r1"])            # предотвращённые ограничения за месяц
        events_avoided += avoided
        alerts += nums * cov * s["r0"] * 1.5                    # предупреждений (1.5 на событие)
        retained_cum += avoided * s["churn_uplift"]             # номеров, не ушедших благодаря этому
        extra_months += retained_cum                            # каждый удержанный платит до конца года
    # новые номера, пришедшие в оператор через приглашения в доп. группы (равномерно во 2-м полугодии)
    churn_months = extra_months
    new_nums = s["extra_groups"] * s["members_per_new_group"] * s["new_member_share"]
    extra_months += new_nums * 3.5                              # в среднем 3.5 оплаченных месяца до конца года
    retention_mln = extra_months * f["rub_per_month"] / 1e6
    support_mln = events_avoided * s["calls_per_event"] * CALL_COST / 1e6
    direct_mln = alerts * DIRECT_COST_PER_ALERT / 1e6
    delta = retention_mln + support_mln - direct_mln
    groups_end = f["groups_nochange"] + s["extra_groups"]
    return dict(extra_paid_months=round(extra_months), months_churn=round(churn_months), months_new=round(extra_months-churn_months), retention_mln=round(retention_mln, 2),
                support_mln=round(support_mln, 2), direct_cost_mln=round(direct_mln, 2), delta_gp_mln=round(delta, 2),
                gp_forecast=round(f["gp_nochange"] + delta, 1), groups_end=groups_end,
                active_last_month=round(groups_end * s["act_share"]), owners_end=f["owners_nochange"],
                activation_14d=s["activation"])


def breakeven(s):
    """Какой должна быть добавка оттока у номеров с ограничением, чтобы закрыть разрыв 6 млн."""
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        t = dict(s, churn_uplift=mid)
        if econ(t)["delta_gp_mln"] < FACTS["gp_target"] - FACTS["gp_nochange"]:
            lo = mid
        else:
            hi = mid
    return hi


def cmd_econ(a):
    out = {k: econ(v) for k, v in SCEN.items()}
    be = breakeven(SCEN["base"])
    if a.json:
        print(json.dumps(dict(scenarios=out, breakeven_churn_uplift=be), ensure_ascii=False, indent=2)); return
    f = FACTS
    print("Разрыв до цели по прибыли: 285 − 279 = 6,0 млн руб. = 12 000 доп. оплаченных месяцев × 500 руб.\n")
    hdr = f"{'показатель':<44}{'без изм.':>10}{'low':>10}{'base':>10}{'high':>10}{'цель':>10}"
    print(hdr); print("-" * len(hdr))
    rows = [("Валовая прибыль, млн руб.", f["gp_nochange"], "gp_forecast", f["gp_target"]),
            ("Активные группы за последний месяц", f["active_nochange"], "active_last_month", f["active_target"]),
            ("Подключённые группы на конец года", f["groups_nochange"], "groups_end", f["groups_target"]),
            ("Подключённые владельцы неск. номеров", f["owners_nochange"], "owners_end", f["owners_target"]),
            ("Активация за 14 дней (посл. квартал)", f["activation_nochange"], "activation_14d", f["activation_target"])]
    for name, nc, key, tgt in rows:
        vals = [out[k][key] for k in ("low", "base", "high")]
        fmt = (lambda x: f"{x:.0%}") if key == "activation_14d" else (lambda x: f"{x:,.1f}" if isinstance(x, float) else f"{x:,}")
        print(f"{name:<44}{fmt(nc):>10}" + "".join(f"{fmt(v):>10}" for v in vals) + f"{fmt(tgt):>10}")
    print("\nСлагаемые прироста прибыли, млн руб.:")
    for k in ("low", "base", "high"):
        o = out[k]
        print(f"  {k:<5} доп. мес.={o['extra_paid_months']:>6,} (удержание {o['months_churn']:,} + новые номера {o['months_new']:,})  оплач. мес.={o['retention_mln']:>5}  поддержка={o['support_mln']:>5}  прямые расходы=−{o['direct_cost_mln']:<5} итог=+{o['delta_gp_mln']}")
    print(f"\nГраница решения (base): цель 285 достижима, если у номеров с ограничением отток выше на ≥ {be:.1%} в месяц"
          f" (в base принято {SCEN['base']['churn_uplift']:.1%}). Это значение нужно узнать в Q1 по данным оператора.")
    inv = PM_COST * DEV_PM
    print(f"Вложения в разработку и запуск ≈ {DEV_PM} чел.-мес × {PM_COST} млн = {inv:.1f} млн руб. (A-14)")
    for k in ("low", "base", "high"):
        d = out[k]["delta_gp_mln"]
        print(f"  {k}: окупаемость в плановом году {'да' if d >= inv else 'нет'} (вклад {d} млн против {inv:.1f} млн)")


OPTIONS = [  # краткая версия strategy.md §4.1 для дашборда
    ("0. Оставить как есть", "продолжать как сейчас", "0", "279 млн", "4 000 вместо 5 000 активных групп уже факт; без действий цель не достигается", False),
    ("1. Предупреждение + перевод", "push при остатке < 15 % + перевод интернета в одно касание, с согласием участника", "≈ 10 чел.-мес. ≈ 3,5 млн", "279,1–280,9 млн", "285 не достигается; 12 % — учебная частота, пользу можно переоценить", True),
    ("2. Общий семейный кабинет", "новый раздел: остатки, начисления, история семьи", "≈ 15–20 чел.-мес.", "≈ 279 (не успеет)", "решает понятность, но не скорость помощи; съедает весь Q2", False),
    ("3. Тариф с авто-перераспределением", "тариф сам переливает свободный остаток", "биллинг + юр. согласование", "неизвестно (G-04)", "лишает организатора контроля, может «съесть» пакет других участников", False),
    ("4. Закрыть направление", "прекратить развитие семейных групп", "экономия ≈ 2–3 млн", "279 + экономия − отток", "закрытие необратимо; удержание групп не измерено (G-02)", False),
]


def cmd_dashboard(a):
    p = _proj(a.slug)
    data = dict(
        generated=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), state=_state(p), claims=_claims(p),
        steps=[[s, n, d] for s, n, d in zip(STEPS, ["Постановка", "Материалы", "Исследование", "Варианты", "Расчёт", "Стратегия", "Пилот", "После решения"],
               ["intake", "collect", "research", "options ⏸", "economics", "strategy ⏸", "pilot", "revise"])],
        facts=FACTS, scen=SCEN, econ={k: econ(v) for k, v in SCEN.items()}, pilot_share=PILOT_SHARE, call_cost=CALL_COST,
        alert_cost=DIRECT_COST_PER_ALERT, pm_cost=PM_COST, dev_pm=DEV_PM,
        options=[list(o) for o in OPTIONS], cost="—")
    f = p / "logs" / "actions.csv"
    if f.exists():
        rows = list(csv.DictReader(f.open(encoding="utf-8")))
        data["cost"] = f"≈{sum(float(r['minutes'] or 0) for r in rows):.0f} мин · ≈{sum(int(r['tokens'] or 0) for r in rows)//1000} тыс. ток."
    html = (ROOT / "tools" / "dashboard_template.html").read_text(encoding="utf-8")
    html = html.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    out = p / "outputs" / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    print(f"Дашборд: {out}\nОткройте в браузере (двойной клик). Данные берутся из state.json, claims.csv и модели econ.")


def cmd_samplesize(a):
    z_a, z_b = 1.959964, 0.841621  # alpha=0.05 двусторонний, мощность 80%
    p0, p1 = a.p0, a.p1
    pb = (p0 + p1) / 2
    n = (z_a * math.sqrt(2 * pb * (1 - pb)) + z_b * math.sqrt(p0 * (1 - p0) + p1 * (1 - p1))) ** 2 / (p0 - p1) ** 2
    deff = 1 + (a.m - 1) * a.icc
    n_num = math.ceil(n * deff)
    groups = math.ceil(n_num / a.m)
    print(f"Номеров на группу сравнения: {math.ceil(n)} без кластеров; с учётом кластеризации (ICC={a.icc}, m={a.m}, DEFF={deff:.2f}): {n_num}")
    print(f"Семейных групп на вариант: {groups}; всего: {2*groups}")
    for w in (4, 6, 8):
        print(f"  набор за {w} нед. → нужно {math.ceil(2*groups/w)} впервые подходящих групп в неделю")


def main():
    ap = argparse.ArgumentParser(prog="sfp", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    x = sp.add_parser("init"); x.add_argument("slug"); x.set_defaults(f=cmd_init)
    x = sp.add_parser("status"); x.add_argument("slug", nargs="?"); x.set_defaults(f=cmd_status)
    x = sp.add_parser("log"); x.add_argument("slug"); x.add_argument("step"); x.add_argument("action")
    x.add_argument("--tokens", type=int, default=0); x.add_argument("--usd", type=float, default=0); x.add_argument("--minutes", type=float, default=0); x.set_defaults(f=cmd_log)
    x = sp.add_parser("cost"); x.add_argument("slug"); x.set_defaults(f=cmd_cost)
    x = sp.add_parser("check"); x.add_argument("slug"); x.set_defaults(f=cmd_check)
    x = sp.add_parser("impact"); x.add_argument("slug"); x.add_argument("claim"); x.set_defaults(f=cmd_impact)
    x = sp.add_parser("econ"); x.add_argument("--json", action="store_true"); x.set_defaults(f=cmd_econ)
    x = sp.add_parser("dashboard"); x.add_argument("slug"); x.set_defaults(f=cmd_dashboard)
    x = sp.add_parser("samplesize"); x.add_argument("--p0", type=float, default=0.12); x.add_argument("--p1", type=float, default=0.09)
    x.add_argument("--icc", type=float, default=0.05); x.add_argument("--m", type=float, default=3); x.set_defaults(f=cmd_samplesize)
    a = ap.parse_args(); a.f(a)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
