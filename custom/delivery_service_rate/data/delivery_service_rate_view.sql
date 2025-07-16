DROP VIEW IF EXISTS delivery_service_rate_monthly;

CREATE VIEW delivery_service_rate_monthly AS (
    SELECT
        ROW_NUMBER() OVER () AS id,  -- champ obligatoire pour Odoo
        to_char(date_done, 'YYYY-MM') AS delivery_month,
        COUNT(*) AS total_deliveries,
        COUNT(CASE WHEN date_done <= scheduled_date THEN 1 END) AS on_time_deliveries,
        ROUND(
            (100.0 * COUNT(CASE WHEN date_done <= scheduled_date THEN 1 END)::float / NULLIF(COUNT(*), 0))::numeric,
            2
        ) AS service_rate
    FROM stock_picking
    WHERE state = 'done'
      AND date_done IS NOT NULL
      AND scheduled_date IS NOT NULL
    GROUP BY to_char(date_done, 'YYYY-MM')
);
