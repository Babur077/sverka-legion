
CREATE TABLE VBASE(
    "Data" DATE,
    "Partner" VARCHAR(200),
    "INN" VARCHAR(50),
    "Service" VARCHAR(50),
    "Status" VARCHAR(50),
    "Sales" numeric,
    "Komissiya" numeric,
    "VID" VARCHAR(50)
)

CREATE TABLE VBANK(
    "Data" DATE,
    "Partner" VARCHAR(200),
    "INN" VARCHAR(50),
    "Summ" numeric,
    "VID" VARCHAR(50)
)

CREATE TABLE VFAKTURA(
    "Data" DATE,
    "Partner" VARCHAR(200),
    "INN" VARCHAR(50),
    "Summ" numeric,
    "VID" VARCHAR(50)
)

CREATE TABLE VIPP(
    "№" int,
    "Partner" VARCHAR(200),
    "INN" VARCHAR(50),
    "VID" VARCHAR(50)
)



SELECT * from vbase
SELECT * from vbank;
SELECT * from vfaktura;
SELECT * from vipp;

drop table vbase;
drop table vbank;
drop table vfaktura;
drop table vipp;

TRUNCATE TABLE VBASE

ALTER TABLE VBASE ADD COLUMN IF NOT EXISTS period_month INT, ADD COLUMN IF NOT EXISTS period_year INT;
ALTER TABLE VBANK ADD COLUMN IF NOT EXISTS period_month INT, ADD COLUMN IF NOT EXISTS period_year INT;
ALTER TABLE VFAKTURA ADD COLUMN IF NOT EXISTS period_month INT, ADD COLUMN IF NOT EXISTS period_year INT;
ALTER TABLE VIPP ADD COLUMN IF NOT EXISTS period_month INT, ADD COLUMN IF NOT EXISTS period_year INT;

CREATE TABLE balance_1c (
    id SERIAL PRIMARY KEY,
    "INN" VARCHAR(50),                  -- Делаем в кавычках и верхнем регистре, как в твоих таблицах
    partner_name VARCHAR(255),
    end_balance NUMERIC(15, 2),
    period_month INT,
    period_year INT,
    UNIQUE("INN", period_month, period_year) -- Защита от дублей при повторной загрузке месяца
);




CREATE OR REPLACE VIEW view_monthly_recon AS
WITH 
-- 1. Считаем реальные продажи из VBASE
baza_summary AS (
    SELECT "INN", 
           SUM(COALESCE("Sales", 0)) as total_sales,
           period_month, period_year
    FROM VBASE
    GROUP BY "INN", period_month, period_year
),
-- 2. Считаем реальные оплаты из VBANK
bank_summary AS (
    SELECT "INN", 
           SUM(COALESCE("Summ", 0)) as total_payments,
           period_month, period_year
    FROM VBANK
    GROUP BY "INN", period_month, period_year
),
-- 3. Считаем фактуры из VFAKTURA
faktura_summary AS (
    SELECT "INN", 
           SUM(COALESCE("Summ", 0)) as total_faktura,
           period_month, period_year
    FROM VFAKTURA
    GROUP BY "INN", period_month, period_year
),
-- 4. Получаем имена партнеров из VIPP
ipp_partners AS (
    SELECT DISTINCT ON ("INN") "INN", "Partner"
    FROM VIPP
),
-- Собираем все ИНН и периоды воедино
all_keys AS (
    SELECT "INN", period_month, period_year FROM baza_summary
    UNION
    SELECT "INN", period_month, period_year FROM bank_summary
    UNION
    SELECT "INN", period_month, period_year FROM faktura_summary
    UNION
    SELECT "INN", period_month, period_year FROM balance_1c
)

-- Финальное сопоставление
SELECT 
    k.period_year as "Год",
    k.period_month as "Месяц",
    k."INN" as "ИНН",
    COALESCE(ipp."Partner", b1c.partner_name, 'Неизвестный партнер') as "Партнер",
    
    COALESCE(bz.total_sales, 0) as "Реал_Продажи",
    COALESCE(bk.total_payments, 0) as "Реал_Оплаты",
    COALESCE(fk.total_faktura, 0) as "Реал_Фактуры",
    
    -- Расчетное сальдо (Продажи - Оплаты)
    (COALESCE(bz.total_sales, 0) - COALESCE(bk.total_payments, 0)) as "Расчетное_Сальдо",
    
    -- Сальдо из 1С
    COALESCE(b1c.end_balance, 0) as "Сальдо_1С",
    
    -- Итог: Расхождение
    ((COALESCE(bz.total_sales, 0) - COALESCE(bk.total_payments, 0)) - COALESCE(b1c.end_balance, 0)) as "Расхождение"

FROM all_keys k
LEFT JOIN ipp_partners ipp ON k."INN" = ipp."INN"
LEFT JOIN baza_summary bz ON k."INN" = bz."INN" AND k.period_month = bz.period_month AND k.period_year = bz.period_year
LEFT JOIN bank_summary bk ON k."INN" = bk."INN" AND k.period_month = bk.period_month AND k.period_year = bk.period_year
LEFT JOIN faktura_summary fk ON k."INN" = fk."INN" AND k.period_month = fk.period_month AND k.period_year = fk.period_year
LEFT JOIN balance_1c b1c ON k."INN" = b1c."INN" AND k.period_month = b1c.period_month AND k.period_year = b1c.period_year;

SELECT * FROM vipp

SELECT * from vbank
SELECT "Data", "INN", "Partner", period_month, period_year from vbank
WHERE period_year = 2026


SELECT * FROM "VBASE";

SELECT * FROM vbase
SELECT * from vbank
SELECT * FROM vfaktura
SELECT * FROM vipp
TRUNCATE TABLE 
    vbank,
    vfaktura,
    vbase,
    vipp
RESTART IDENTITY CASCADE;

select * from audit_log


truncate table audit_log
DELETE table audit_log

ALTER TABLE vbase ALTER COLUMN "Partner" TYPE TEXT;
ALTER TABLE vbase ALTER COLUMN "Service" TYPE TEXT;
ALTER TABLE vbase ALTER COLUMN "Status" TYPE TEXT;
ALTER TABLE vbase ALTER COLUMN "VID" TYPE TEXT;

-- 2. Исправляем таблицу VBANK
ALTER TABLE vbank ALTER COLUMN "Partner" TYPE TEXT;
ALTER TABLE vbank ALTER COLUMN "VID" TYPE TEXT;

-- 3. Исправляем таблицу VFAKTURA (где как раз споткнулся Сентябрь)
ALTER TABLE vfaktura ALTER COLUMN "Partner" TYPE TEXT;
ALTER TABLE vfaktura ALTER COLUMN "VID" TYPE TEXT;

-- 4. Исправляем таблицу VIPP
ALTER TABLE vipp ALTER COLUMN "Partner" TYPE TEXT;
ALTER TABLE vipp ALTER COLUMN "VID" TYPE TEXT;







-- 1. Удаляем старое представление, чтобы оно не блокировало таблицы
DROP VIEW IF EXISTS public.view_monthly_reconciliation CASCADE;

-- 2. Сносим ВСЕ старые таблицы (и капсом, и строчными), чтобы навести идеальный порядок
DROP TABLE IF EXISTS public."VBASE", public.vbase CASCADE;
DROP TABLE IF EXISTS public."VBANK", public.vbank CASCADE;
DROP TABLE IF EXISTS public."VFAKTURA", public.vfaktura CASCADE;
DROP TABLE IF EXISTS public."VIPP", public.vipp CASCADE;

-- 3. Создаем новые чистые таблицы с запасом под строки (VARCHAR(200))
CREATE TABLE public.vbase (
    "Data" DATE,
    "Partner" VARCHAR(200),
    "INN" VARCHAR(50),
    "Service" VARCHAR(200),
    "Status" VARCHAR(200),
    "Sales" NUMERIC,
    "Komissiya" NUMERIC,
    "VID" VARCHAR(200),
    period_month INT,
    period_year INT
);

CREATE TABLE public.vbank (
    "Data" DATE,
    "Partner" VARCHAR(200),
    "INN" VARCHAR(50),
    "Summ" NUMERIC,
    "VID" VARCHAR(200),
    period_month INT,
    period_year INT
);

CREATE TABLE public.vfaktura (
    "Data" DATE,
    "Partner" VARCHAR(200),
    "INN" VARCHAR(50),
    "Summ" NUMERIC,
    "VID" VARCHAR(200),
    period_month INT,
    period_year INT
);

CREATE TABLE public.vipp (
    "№" INT,
    "Partner" VARCHAR(200),
    "INN" VARCHAR(50),
    "VID" VARCHAR(200),
    period_month INT,
    period_year INT
);

-- 4. Сразу возвращаем на место красивое и чистое представление
CREATE OR REPLACE VIEW public.view_monthly_reconciliation AS
SELECT 
    coalesce(b."Partner", f."Partner", p."Partner", c."partner_name") AS "Partner",
    coalesce(b."INN", f."INN", p."INN", c."INN") AS "INN",
    b."Summ" AS bank_summ,
    f."Summ" AS faktura_summ,
    c.end_balance AS balance_1c_summ,
    b.period_month,
    b.period_year
FROM public.vbank b
FULL JOIN public.vfaktura f ON b."INN" = f."INN" AND b.period_month = f.period_month AND b.period_year = f.period_year
FULL JOIN public.vipp p ON b."INN" = p."INN" AND b.period_month = p.period_month AND b.period_year = p.period_year
FULL JOIN public.balance_1c c ON b."INN" = c."INN";




-- Полностью очищаем таблицы от старого мусора
TRUNCATE TABLE public.vbase CASCADE;
TRUNCATE TABLE public.vbank CASCADE;
TRUNCATE TABLE public.vfaktura CASCADE;
TRUNCATE TABLE public.vipp CASCADE;

SELECT * FROM vbase;
SELECT * from vbank;
SELECT * FROM vfaktura;
SELECT * FROM vipp;

SELECT * FROM vfaktura
WHERE period_year = '2026'

-- Проверяем, есть ли продажи за февраль 2025
SELECT * FROM public.vfaktura 
WHERE period_month = 2 AND period_year = 2025 
LIMIT 10;

CREATE VIEW public.view_monthly_reconciliation AS
WITH prepared_bank AS (
    SELECT 
        "Partner",
        REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', '') AS clean_inn,
        "Summ" AS bank_summ,
        period_month,
        period_year
    FROM public.vbank
),
prepared_faktura AS (
    SELECT 
        "Partner",
        REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', '') AS clean_inn,
        "Summ" AS faktura_summ,
        period_month,
        period_year
    FROM public.vfaktura
),
prepared_1c AS (
    SELECT 
        partner_name,
        REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', '') AS clean_inn,
        end_balance AS balance_1c_summ
    FROM public.balance_1c
),
all_partners AS (
    SELECT clean_inn, "Partner", period_month, period_year FROM prepared_bank
    UNION
    SELECT clean_inn, "Partner", period_month, period_year FROM prepared_faktura
)
SELECT 
    COALESCE(b."Partner", f."Partner", c.partner_name, ap."Partner") AS "Partner",
    -- Преобразуем тип обратно в varchar(50), чтобы база не ругалась
    ap.clean_inn::character varying(50) AS "INN",
    COALESCE(b.bank_summ, 0) AS bank_summ,
    COALESCE(f.faktura_summ, 0) AS faktura_summ,
    COALESCE(c.balance_1c_summ, 0) AS balance_1c_summ,
    ap.period_month,
    ap.period_year
FROM all_partners ap
LEFT JOIN prepared_bank b ON ap.clean_inn = b.clean_inn AND ap.period_month = b.period_month AND ap.period_year = b.period_year
LEFT JOIN prepared_faktura f ON ap.clean_inn = f.clean_inn AND ap.period_month = f.period_month AND ap.period_year = f.period_year
LEFT JOIN prepared_1c c ON ap.clean_inn = c.clean_inn;

SELECT Sum("Summ")
from vfaktura
where "Data" = '2025-01-31'
OR "Data" = '2025-01-01'


SELECT * FROM vfaktura

SELECT SUM(faktura_val) FROM view_monthly_reconciliation WHERE period_month = 1 AND period_year = 2025;


SELECT 
    COALESCE("INN", '-') AS "ИНН",
    "Partner" AS "Партнер",
    SUM(faktura_val) AS "Сумма_Фактур"
FROM view_monthly_reconciliation
WHERE period_month = 1  -- Январь
  AND period_year = 2025 -- Проверьте год (2025 или 2026!)
GROUP BY COALESCE("INN", '-'), "Partner"
ORDER BY "Сумма_Фактур" DESC;


select * from vfaktura
WHERE "Partner"='RAXMAT-TRAVEL'

select * from vfaktura
WHERE "INN"='310458627.0'
or "Partner"='RAXMAT-TRAVEL'


select * FROM vfaktura 
WHERE "period_month" = 1 
  AND "period_year" = 2025;

SELECT FROM vfaktura 
WHERE doc_number = '882' 
  AND doc_date = '2024-12-31' 
  AND faktura_val = 186065.12;



DROP VIEW IF EXISTS public.view_monthly_reconciliation;

CREATE VIEW public.view_monthly_reconciliation AS
WITH prepared_base AS (
    SELECT 
        "Partner",
        REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', '') AS clean_inn,
        SUM(COALESCE("Sales", 0)) AS sales_summ,
        SUM(COALESCE("Komissiya", 0)) AS komissiya_summ,
        period_month,
        period_year
    FROM public.vbase
    GROUP BY "Partner", REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', ''), period_month, period_year
),
prepared_bank AS (
    SELECT 
        "Partner",
        REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', '') AS clean_inn,
        SUM(COALESCE("Summ", 0)) AS bank_summ,
        period_month,
        period_year
    FROM public.vbank
    GROUP BY "Partner", REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', ''), period_month, period_year
),
prepared_faktura AS (
    SELECT 
        "Partner",
        REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', '') AS clean_inn,
        SUM(COALESCE("Summ", 0)) AS faktura_summ,
        period_month,
        period_year
    FROM public.vfaktura
    GROUP BY "Partner", REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', ''), period_month, period_year
),
prepared_1c AS (
    SELECT 
        partner_name,
        REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', '') AS clean_inn,
        SUM(COALESCE(end_balance, 0)) AS balance_1c_summ
    FROM public.balance_1c
    GROUP BY partner_name, REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', '')
),
all_periods_partners AS (
    SELECT clean_inn, "Partner", period_month, period_year FROM prepared_base
    UNION
    SELECT clean_inn, "Partner", period_month, period_year FROM prepared_bank
    UNION
    SELECT clean_inn, "Partner", period_month, period_year FROM prepared_faktura
)
SELECT 
    COALESCE(bs.sales_summ, 0) AS payment_val,
    COALESCE(bk.bank_summ, 0) AS bank_val,
    COALESCE(fk.faktura_summ, 0) AS faktura_val,
    COALESCE(bs.komissiya_summ, 0) AS komissiya_val,
    COALESCE(c.balance_1c_summ, 0) AS balance_1c_val,
    COALESCE(bs."Partner", bk."Partner", fk."Partner", c.partner_name, ap."Partner") AS "Partner",
    ap.clean_inn::character varying(50) AS "INN",
    ap.period_month,
    ap.period_year
FROM all_periods_partners ap
LEFT JOIN prepared_base bs ON ap.clean_inn = bs.clean_inn AND ap.period_month = bs.period_month AND ap.period_year = bs.period_year
LEFT JOIN prepared_bank bk ON ap.clean_inn = bk.clean_inn AND ap.period_month = bk.period_month AND ap.period_year = bk.period_year
LEFT JOIN prepared_faktura fk ON ap.clean_inn = fk.clean_inn AND ap.period_month = fk.period_month AND ap.period_year = fk.period_year
LEFT JOIN prepared_1c c ON ap.clean_inn = c.clean_inn;


select * from vfaktura












DROP VIEW IF EXISTS public.view_monthly_reconciliation;

CREATE VIEW public.view_monthly_reconciliation AS
WITH prepared_base AS (
    SELECT 
        TRIM("Partner") AS clean_partner,
        REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', '') AS clean_inn,
        SUM(COALESCE("Sales", 0)) AS sales_summ,
        SUM(COALESCE("Komissiya", 0)) AS komissiya_summ,
        period_month,
        period_year
    FROM public.vbase
    GROUP BY TRIM("Partner"), REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', ''), period_month, period_year
),
prepared_bank AS (
    SELECT 
        TRIM("Partner") AS clean_partner,
        REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', '') AS clean_inn,
        SUM(COALESCE("Summ", 0)) AS bank_summ,
        period_month,
        period_year
    FROM public.vbank
    GROUP BY TRIM("Partner"), REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', ''), period_month, period_year
),
prepared_faktura AS (
    SELECT 
        TRIM("Partner") AS clean_partner,
        REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', '') AS clean_inn,
        SUM(COALESCE("Summ", 0)) AS faktura_summ,
        period_month,
        period_year
    FROM public.vfaktura
    GROUP BY TRIM("Partner"), REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', ''), period_month, period_year
),
prepared_1c AS (
    SELECT 
        TRIM(partner_name) AS clean_partner,
        REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', '') AS clean_inn,
        SUM(COALESCE(end_balance, 0)) AS balance_1c_summ
    FROM public.balance_1c
    GROUP BY TRIM(partner_name), REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', '')
),
all_distinct_partners AS (
    SELECT clean_partner, clean_inn, period_month, period_year FROM prepared_base
    UNION
    SELECT clean_partner, clean_inn, period_month, period_year FROM prepared_bank
    UNION
    SELECT clean_partner, clean_inn, period_month, period_year FROM prepared_faktura
)
SELECT 
    ap.clean_partner AS "Partner",
    CASE 
        WHEN ap.clean_inn = 'nan' OR ap.clean_inn = '' THEN NULL 
        ELSE ap.clean_inn::character varying(50) 
    END AS "INN",
    COALESCE(bs.sales_summ, 0) AS payment_val,
    COALESCE(bk.bank_summ, 0) AS bank_val,
    COALESCE(fk.faktura_summ, 0) AS faktura_val,
    COALESCE(bs.komissiya_summ, 0) AS komissiya_val,
    COALESCE(c.balance_1c_summ, 0) AS balance_1c_val,
    ap.period_month,
    ap.period_year
FROM all_distinct_partners ap
LEFT JOIN prepared_base bs ON ap.clean_partner = bs.clean_partner AND ap.period_month = bs.period_month AND ap.period_year = bs.period_year
LEFT JOIN prepared_bank bk ON ap.clean_partner = bk.clean_partner AND ap.period_month = bk.period_month AND ap.period_year = bk.period_year
LEFT JOIN prepared_faktura fk ON ap.clean_partner = fk.clean_partner AND ap.period_month = fk.period_month AND ap.period_year = fk.period_year
LEFT JOIN prepared_1c c ON ap.clean_partner = c.clean_partner;

select * from vbase
where
    "INN" = '307806232'
    and "Data" = '2025-03-01'



















    DROP VIEW IF EXISTS public.view_monthly_reconciliation;

CREATE VIEW public.view_monthly_reconciliation AS
WITH prepared_base AS (
    SELECT 
        TRIM("Partner") AS clean_partner,
        REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', '') AS clean_inn,
        
        -- 🎯 Условие 1 и 2 для Sales (Берем только SUCCEEDED. Если REVERTED — продажи обнуляем)
        SUM(CASE 
            WHEN TRIM("Status") = 'SUCCEEDED' THEN COALESCE("Sales", 0)
            ELSE 0 
        END) AS sales_summ,
        
        -- 🎯 Условие для Komissiya (Учитываем и при SUCCEEDED, и при REVERTED)
        SUM(CASE 
            WHEN TRIM("Status") IN ('SUCCEEDED', 'REVERTED') THEN COALESCE("Komissiya", 0)
            ELSE 0 
        END) AS komissiya_summ,
        
        period_month,
        period_year
    FROM public.vbase
    GROUP BY TRIM("Partner"), REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', ''), period_month, period_year
),
prepared_bank AS (
    SELECT 
        TRIM("Partner") AS clean_partner,
        REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', '') AS clean_inn,
        SUM(COALESCE("Summ", 0)) AS bank_summ,
        period_month,
        period_year
    FROM public.vbank
    GROUP BY TRIM("Partner"), REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', ''), period_month, period_year
),
prepared_faktura AS (
    SELECT 
        TRIM("Partner") AS clean_partner,
        REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', '') AS clean_inn,
        SUM(COALESCE("Summ", 0)) AS faktura_summ,
        period_month,
        period_year
    FROM public.vfaktura
    GROUP BY TRIM("Partner"), REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', ''), period_month, period_year
),
prepared_1c AS (
    SELECT 
        TRIM(partner_name) AS clean_partner,
        REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', '') AS clean_inn,
        SUM(COALESCE(end_balance, 0)) AS balance_1c_summ
    FROM public.balance_1c
    GROUP BY TRIM(partner_name), REGEXP_REPLACE(TRIM(CAST("INN" AS TEXT)), '\.0$', '')
),
all_distinct_partners AS (
    SELECT clean_partner, clean_inn, period_month, period_year FROM prepared_base
    UNION
    SELECT clean_partner, clean_inn, period_month, period_year FROM prepared_bank
    UNION
    SELECT clean_partner, clean_inn, period_month, period_year FROM prepared_faktura
)
SELECT 
    ap.clean_partner AS "Partner",
    CASE 
        WHEN ap.clean_inn = 'nan' OR ap.clean_inn = '' THEN NULL 
        ELSE ap.clean_inn::character varying(50) 
    END AS "INN",
    COALESCE(bs.sales_summ, 0) AS payment_val,
    COALESCE(bk.bank_summ, 0) AS bank_val,
    COALESCE(fk.faktura_summ, 0) AS faktura_val,
    COALESCE(bs.komissiya_summ, 0) AS komissiya_val,
    COALESCE(c.balance_1c_summ, 0) AS balance_1c_val,
    ap.period_month,
    ap.period_year
FROM all_distinct_partners ap
LEFT JOIN prepared_base bs ON ap.clean_partner = bs.clean_partner AND ap.period_month = bs.period_month AND ap.period_year = bs.period_year
LEFT JOIN prepared_bank bk ON ap.clean_partner = bk.clean_partner AND ap.period_month = bk.period_month AND ap.period_year = bk.period_year
LEFT JOIN prepared_faktura fk ON ap.clean_partner = fk.clean_partner AND ap.period_month = fk.period_month AND ap.period_year = fk.period_year
LEFT JOIN prepared_1c c ON ap.clean_partner = c.clean_partner;
    






-- 1. Стираем старую структуру
DROP VIEW IF EXISTS view_detailed_reconciliation;

-- 2. Создаем чистую вьюху с фиксированными типами данных
CREATE VIEW view_detailed_reconciliation AS

-- Данные из 1С / Продажи (Таблица vbase)
SELECT 
    inn::varchar AS "INN",
    doc_date::date AS doc_date,
    '1С: Операция'::varchar AS doc_type,
    doc_num::varchar AS doc_number,
    amount::numeric AS payment_val,
    0.0::numeric AS bank_val,
    0.0::numeric AS faktura_val,
    0.0::numeric AS komissiya_val,
    period_month::int AS period_month,
    period_year::int AS period_year
FROM vbase

UNION ALL

-- Данные из Банка (Таблица vbank)
SELECT 
    inn::varchar AS "INN",
    doc_date::date AS doc_date,
    'Банк: Выписка'::varchar AS doc_type, -- Исправлено: просто текст, без обращения к несуществующему столбцу
    doc_num::varchar AS doc_number,
    0.0::numeric AS payment_val,
    amount::numeric AS bank_val,
    0.0::numeric AS faktura_val,
    0.0::numeric AS komissiya_val,
    period_month::int AS period_month,
    period_year::int AS period_year
FROM vbank

UNION ALL

-- Данные по Счет-фактурам (Таблица vfaktura)
SELECT 
    inn::varchar AS "INN",
    doc_date::date AS doc_date,
    'Счет-фактура'::varchar AS doc_type,
    doc_num::varchar AS doc_number,
    0.0::numeric AS payment_val,
    0.0::numeric AS bank_val,
    amount::numeric AS faktura_val,
    0.0::numeric AS komissiya_val,
    period_month::int AS period_month,
    period_year::int AS period_year
FROM vfaktura

UNION ALL

-- Данные PAYNET / Комиссия (Таблица vipp)
SELECT 
    inn::varchar AS "INN",
    doc_date::date AS doc_date,
    'PAYNET: Комиссия'::varchar AS doc_type,
    doc_num::varchar AS doc_number,
    0.0::numeric AS payment_val,
    0.0::numeric AS bank_val,
    0.0::numeric AS faktura_val,
    amount::numeric AS komissiya_val,
    period_month::int AS period_month,
    period_year::int AS period_year
FROM vipp;










-- 1. Стираем старую структуру
DROP VIEW IF EXISTS view_detailed_reconciliation;

-- 2. Создаем чистую вьюху с фиксированными типами данных
CREATE VIEW view_detailed_reconciliation AS

-- Данные из 1С / Продажи (Таблица vbase)
SELECT 
    inn::varchar AS "INN",
    doc_date::date AS doc_date,
    '1С: Операция'::varchar AS doc_type,
    doc_num::varchar AS doc_number,
    amount::numeric AS payment_val,
    0.0::numeric AS bank_val,
    0.0::numeric AS faktura_val,
    0.0::numeric AS komissiya_val,
    period_month::int AS period_month,
    period_year::int AS period_year
FROM vbase

UNION ALL

-- Данные из Банка (Таблица vbank)
SELECT 
    inn::varchar AS "INN",
    doc_date::date AS doc_date,
    'Банк: Выписка'::varchar AS doc_type, -- Исправлено: просто текст, без обращения к несуществующему столбцу
    doc_num::varchar AS doc_number,
    0.0::numeric AS payment_val,
    amount::numeric AS bank_val,
    0.0::numeric AS faktura_val,
    0.0::numeric AS komissiya_val,
    period_month::int AS period_month,
    period_year::int AS period_year
FROM vbank

UNION ALL

-- Данные по Счет-фактурам (Таблица vfaktura)
SELECT 
    inn::varchar AS "INN",
    doc_date::date AS doc_date,
    'Счет-фактура'::varchar AS doc_type,
    doc_num::varchar AS doc_number,
    0.0::numeric AS payment_val,
    0.0::numeric AS bank_val,
    amount::numeric AS faktura_val,
    0.0::numeric AS komissiya_val,
    period_month::int AS period_month,
    period_year::int AS period_year
FROM vfaktura

UNION ALL

-- Данные PAYNET / Комиссия (Таблица vipp)
SELECT 
    inn::varchar AS "INN",
    doc_date::date AS doc_date,
    'PAYNET: Комиссия'::varchar AS doc_type,
    doc_num::varchar AS doc_number,
    0.0::numeric AS payment_val,
    0.0::numeric AS bank_val,
    0.0::numeric AS faktura_val,
    amount::numeric AS komissiya_val,
    period_month::int AS period_month,
    period_year::int AS period_year
FROM vipp;



-- 1. Очищаем ИНН в таблице vfaktura
UPDATE vfaktura
SET "INN" = split_part("INN", '.', 1)
WHERE "INN" LIKE '%.0';

-- 2. Очищаем ИНН в таблице vipp
UPDATE vipp
SET "INN" = split_part("INN", '.', 1)
WHERE "INN" LIKE '%.0';

SELECT * FROM vfaktura
SELECT * FROM vipp

SELECT * FROM vfaktura
where "period_month" = 1
and "Summ" = 186065.12

SELECT * FROM vfaktura
where "Partner" = 'RAXMAT-TRAVEL'

SELECT * from vipp
where "INN" = '203691761';

-- Удаляем фантомные записи изо всех таблиц базы данных
DELETE FROM vbase WHERE "INN" = '203691761';
DELETE FROM vfaktura WHERE "INN" = '203691761';
DELETE FROM vbank WHERE "INN" = '203691761';
DELETE FROM vipp WHERE "INN" = '203691761';

select * from vfaktura

select sum("Summ")
from vfaktura


SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'vipp';

№ Partner INN VID period_month period_year

select * from vbank
where "INN" = '102095715'

SELECT * from vfaktura
where "period_month" = '12'

SELECT sum("Summ")
FROM vfaktura
where "period_month" = '12';

SELECT * FROM vbase
where "INN" = '310441292'

SELECT * FROM vfaktura

select * from balance_1c



SELECT pg_get_viewdef('view_monthly_reconciliation'::regclass, true);




















-- Пересборка вьюхи на VID вместо имени/ИНН.
-- Учитываются только строки, у которых VID реально есть в справочнике vipp
-- (это автоматически отсекает NULL VID и "испорченные" VID типа 'V107(другой договор)').

CREATE OR REPLACE VIEW view_monthly_reconciliation AS
WITH vipp_canon AS (
    -- Один "канонический" Partner/ИНН на каждый VID (для отображения).
    -- Если на VID привязано два ИНН (обычный ИНН + ПИНФЛ), предпочитаем короткий
    -- (обычный ИНН, 9 знаков) — он более читаемый, чем 14-значный ПИНФЛ.
    SELECT DISTINCT ON (vipp."VID")
        vipp."VID" AS vid,
        TRIM(BOTH FROM vipp."Partner") AS clean_partner,
        regexp_replace(TRIM(BOTH FROM vipp."INN"::text), '\.0$', '') AS clean_inn
    FROM vipp
    WHERE vipp."VID" IS NOT NULL
    ORDER BY vipp."VID",
             length(regexp_replace(TRIM(BOTH FROM vipp."INN"::text), '\.0$', '')) ASC
),
prepared_base AS (
    SELECT
        vbase."VID" AS vid,
        sum(
            CASE
                WHEN TRIM(BOTH FROM vbase."Status") = 'SUCCEEDED' THEN COALESCE(vbase."Sales", 0::numeric)
                ELSE 0::numeric
            END
        ) AS sales_summ,
        sum(
            CASE
                WHEN TRIM(BOTH FROM vbase."Status") = ANY (ARRAY['SUCCEEDED'::text, 'REVERTED'::text])
                THEN COALESCE(vbase."Komissiya", 0::numeric)
                ELSE 0::numeric
            END
        ) AS komissiya_summ,
        vbase.period_month,
        vbase.period_year
    FROM vbase
    INNER JOIN vipp_canon vc ON vbase."VID" = vc.vid
    GROUP BY vbase."VID", vbase.period_month, vbase.period_year
),
prepared_bank AS (
    SELECT
        vbank."VID" AS vid,
        sum(COALESCE(vbank."Summ", 0::numeric)) AS bank_summ,
        vbank.period_month,
        vbank.period_year
    FROM vbank
    INNER JOIN vipp_canon vc ON vbank."VID" = vc.vid
    GROUP BY vbank."VID", vbank.period_month, vbank.period_year
),
prepared_faktura AS (
    SELECT
        vfaktura."VID" AS vid,
        sum(COALESCE(vfaktura."Summ", 0::numeric)) AS faktura_summ,
        vfaktura.period_month,
        vfaktura.period_year
    FROM vfaktura
    INNER JOIN vipp_canon vc ON vfaktura."VID" = vc.vid
    GROUP BY vfaktura."VID", vfaktura.period_month, vfaktura.period_year
),
prepared_1c AS (
    -- В balance_1c нет VID — матчим через ИНН -> vipp -> VID.
    SELECT
        vc.vid AS vid,
        sum(COALESCE(balance_1c.end_balance, 0::numeric)) AS balance_1c_summ
    FROM balance_1c
    INNER JOIN vipp_canon vc
        ON regexp_replace(TRIM(BOTH FROM balance_1c."INN"::text), '\.0$', '') = vc.clean_inn
    GROUP BY vc.vid
),
all_distinct_vids AS (
    SELECT vid, period_month, period_year FROM prepared_base
    UNION
    SELECT vid, period_month, period_year FROM prepared_bank
    UNION
    SELECT vid, period_month, period_year FROM prepared_faktura
)
SELECT
    vc.clean_partner AS "Partner",
    CASE
        WHEN vc.clean_inn = 'nan' OR vc.clean_inn = '' THEN NULL::character varying
        ELSE vc.clean_inn::character varying(50)
    END AS "INN",
    COALESCE(bs.sales_summ, 0::numeric) AS payment_val,
    COALESCE(bk.bank_summ, 0::numeric) AS bank_val,
    COALESCE(fk.faktura_summ, 0::numeric) AS faktura_val,
    COALESCE(bs.komissiya_summ, 0::numeric) AS komissiya_val,
    COALESCE(c.balance_1c_summ, 0::numeric) AS balance_1c_val,
    ap.period_month,
    ap.period_year,
    ap.vid AS "VID"
FROM all_distinct_vids ap
JOIN vipp_canon vc ON ap.vid = vc.vid
LEFT JOIN prepared_base bs ON ap.vid = bs.vid AND ap.period_month = bs.period_month AND ap.period_year = bs.period_year
LEFT JOIN prepared_bank bk ON ap.vid = bk.vid AND ap.period_month = bk.period_month AND ap.period_year = bk.period_year
LEFT JOIN prepared_faktura fk ON ap.vid = fk.vid AND ap.period_month = fk.period_month AND ap.period_year = fk.period_year
LEFT JOIN prepared_1c c ON ap.vid = c.vid;





-- Отдельный справочник: один канонический Partner/ИНН на каждый VID.
-- Используется запросами в app.py (вкладки Продажи/Фактуры/Оплаты, поиск по ИНН
-- на странице помесячного отчёта), чтобы не дублировать эту логику в каждом запросе.
-- view_monthly_reconciliation не трогаем — она уже работает со своей встроенной копией этой логики.

CREATE OR REPLACE VIEW vipp_canon AS
SELECT
    "VID",
    "Partner",
    CASE WHEN "INN" IN ('nan', '') THEN NULL ELSE "INN" END AS "INN"
FROM (
    SELECT DISTINCT ON (vipp."VID")
        vipp."VID" AS "VID",
        TRIM(BOTH FROM vipp."Partner") AS "Partner",
        regexp_replace(TRIM(BOTH FROM vipp."INN"::text), '\.0$', '') AS "INN"
    FROM vipp
    WHERE vipp."VID" IS NOT NULL
    ORDER BY vipp."VID",
             -- если на VID два ИНН (обычный + ПИНФЛ) — предпочитаем короткий (обычный ИНН)
             length(regexp_replace(TRIM(BOTH FROM vipp."INN"::text), '\.0$', '')) ASC
) t;

select * from vfaktura
where "VID" = 'V1'

select * from saldo_initial

-- Есть ли VID из vbank в vipp_canon?
SELECT COUNT(*) 
FROM vbank b
INNER JOIN vipp_canon vc ON b."VID" = vc."VID"
WHERE b.period_month = 2 AND b.period_year = 2026;

SELECT b."VID", vc."VID"
FROM vbank b
LEFT JOIN vipp_canon vc ON b."VID" = vc."VID"
WHERE b.period_month = 2 AND b.period_year = 2026
LIMIT 10;
SELECT "VID" FROM vbank LIMIT 5;
SELECT "VID" FROM vipp LIMIT 5;

select * saldo_initial
select * from vipp_canon



ALTER TABLE vbase    ADD COLUMN id SERIAL PRIMARY KEY;
ALTER TABLE vfaktura ADD COLUMN id SERIAL PRIMARY KEY;
ALTER TABLE vbank    ADD COLUMN id SERIAL PRIMARY KEY;


select * from vbase
where "VID" = 'V359'


SELECT column_name FROM information_schema.columns WHERE table_name = 'vbase';
SELECT column_name FROM information_schema.columns WHERE table_name = 'vfaktura';
SELECT column_name FROM information_schema.columns WHERE table_name = 'vbank';

select * from vbase
where "VID" = 'V359'
+where "VID" 'V232'


select * from vbank

select * from saldo_initial

SELECT
    column_name,
    data_type
FROM information_schema.columns
WHERE table_name = 'vbank'
  AND column_name = 'Data';

SELECT vid, saldo FROM saldo_initial WHERE vid = 'V1000';
SELECT vid, saldo FROM saldo_initial WHERE LOWER(vid) = 'v1000';


  truncate table vbase
select * from VBANK


  select count('INN') from vbank

  select * from vbank where "INN" = '203691761'
  select * from vipp_canon 311679304

TRUNCATE TABLE vbase RESTART IDENTITY CASCADE;
TRUNCATE TABLE vbank RESTART IDENTITY CASCADE;
TRUNCATE TABLE vfaktura RESTART IDENTITY CASCADE;



TRUNCATE TABLE vbase RESTART IDENTITY CASCADE;
TRUNCATE TABLE vbank RESTART IDENTITY CASCADE;
TRUNCATE TABLE vfaktura RESTART IDENTITY CASCADE;
TRUNCATE TABLE vipp RESTART IDENTITY CASCADE;
TRUNCATE TABLE saldo_initial RESTART IDENTITY CASCADE;
TRUNCATE TABLE audit_log RESTART IDENTITY CASCADE;

SELECT period_month, period_year, COUNT(*) 
FROM vbank 
GROUP BY period_month, period_year 
ORDER BY period_year, period_month;

select * from balance_1c

select * from saldo_initial
where "inn" = '312083784';



SELECT pg_get_viewdef('view_monthly_reconciliation'::regclass, true);

select * from balance_1c
where "INN" = '300317925'
\o viewdef.txt
SELECT pg_get_viewdef('view_monthly_reconciliation'::regclass, true);
\o

select * from saldo_initial
where "inn" = 303237438

select * from balance_1c


select * from vbase
where "INN" = '200899276'


