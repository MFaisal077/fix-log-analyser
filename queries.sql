-- Support checks on the execution reports, written for SQLite.
-- Run them all with:  sqlite3 fix.db < queries.sql

.headers on
.mode column

-- 1. Which firms are getting rejects, and why?
--    WHERE picks the rejected rows before grouping, and HAVING keeps only
--    firms with more than 2, which suggests a problem on their side.
SELECT firm, COUNT(*) AS rejects, GROUP_CONCAT(DISTINCT text) AS reasons
FROM executions
WHERE exec_type = '8'
GROUP BY firm
HAVING COUNT(*) > 2
ORDER BY rejects DESC;

-- 2. Traded shares and value per symbol (prices are in pence).
SELECT symbol,
       SUM(last_qty)           AS shares,
       SUM(last_qty * last_px) AS value_pence
FROM executions
WHERE exec_type IN ('1', '2')
GROUP BY symbol
ORDER BY value_pence DESC;

-- 3. Reconciliation: CumQty + LeavesQty should always equal OrderQty.
--    Cancelled (4) and rejected (8) reports set LeavesQty to 0 on purpose.
SELECT time, firm, clordid, cum_qty, leaves_qty, order_qty
FROM executions
WHERE exec_type NOT IN ('4', '8')
  AND cum_qty + leaves_qty <> order_qty;

-- 4. Where did each order end up? The latest report per venue OrderID,
--    found with a window function.
WITH ranked AS (
    SELECT order_id, firm, symbol, exec_type, cum_qty, order_qty,
           ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY time DESC) AS rn
    FROM executions
    WHERE order_id <> 'NONE'
)
SELECT CASE exec_type
           WHEN '0' THEN 'Open, no fills'
           WHEN '1' THEN 'Open, partly filled'
           WHEN '2' THEN 'Filled'
           WHEN '4' THEN 'Cancelled'
       END AS final_state,
       COUNT(*) AS orders
FROM ranked
WHERE rn = 1
GROUP BY final_state
ORDER BY orders DESC;

-- 5. Orders still open at the end of the day, per firm.
WITH latest AS (
    SELECT order_id, firm, exec_type, leaves_qty,
           ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY time DESC) AS rn
    FROM executions
    WHERE order_id <> 'NONE'
)
SELECT firm, COUNT(*) AS open_orders, SUM(leaves_qty) AS open_shares
FROM latest
WHERE rn = 1 AND exec_type IN ('0', '1')
GROUP BY firm;
