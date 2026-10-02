const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const express = require("express");
const { DatabaseSync } = require("node:sqlite");

const ROOT = __dirname;
const DB_PATH = path.join(ROOT, "sales.db");
const PORT = process.env.PORT || 3055;

function importIfNeeded() {
  if (fs.existsSync(DB_PATH)) return;
  console.log("sales.db not found. Importing Sales.xlsx ...");
  const commands = [
    ["python", ["import-sales.py"]],
    ["py", ["-3", "import-sales.py"]],
  ];
  let ok = false;
  for (const [cmd, args] of commands) {
    const result = spawnSync(cmd, args, { cwd: ROOT, stdio: "inherit" });
    if (result.status === 0 && fs.existsSync(DB_PATH)) {
      ok = true;
      break;
    }
  }
  if (!ok) {
    throw new Error("Could not import Sales.xlsx. Run: python import-sales.py");
  }
}

function whereFrom(query) {
  const clauses = [];
  const params = [];
  if (query.year) {
    clauses.push("year = ?");
    params.push(Number(query.year));
  }
  if (query.country) {
    clauses.push("country = ?");
    params.push(query.country);
  }
  if (query.category) {
    clauses.push("product_category = ?");
    params.push(query.category);
  }
  return {
    sql: clauses.length ? `WHERE ${clauses.join(" AND ")}` : "",
    params,
  };
}

function all(db, sql, params = []) {
  return db.prepare(sql).all(...params);
}

function get(db, sql, params = []) {
  return db.prepare(sql).get(...params);
}

importIfNeeded();
const db = new DatabaseSync(DB_PATH, { readOnly: true });
const app = express();

app.use(express.static(path.join(ROOT, "public")));

app.get("/api/filters", (_req, res) => {
  res.json({
    years: all(db, "SELECT DISTINCT year FROM sales ORDER BY year").map((r) => r.year),
    countries: all(db, "SELECT DISTINCT country FROM sales ORDER BY country").map(
      (r) => r.country
    ),
    categories: all(
      db,
      "SELECT DISTINCT product_category FROM sales ORDER BY product_category"
    ).map((r) => r.product_category),
  });
});

app.get("/api/dashboard", (req, res) => {
  const { sql, params } = whereFrom(req.query);
  const kpis = get(
    db,
    `SELECT
       COUNT(*) AS orders,
       COALESCE(SUM(order_quantity), 0) AS units,
       COALESCE(SUM(revenue), 0) AS revenue,
       COALESCE(SUM(profit), 0) AS profit,
       COALESCE(SUM(cost), 0) AS cost
     FROM sales ${sql}`,
    params
  );
  kpis.margin = kpis.revenue ? (kpis.profit / kpis.revenue) * 100 : 0;

  const monthOrder = `CASE month
    WHEN 'January' THEN 1 WHEN 'February' THEN 2 WHEN 'March' THEN 3
    WHEN 'April' THEN 4 WHEN 'May' THEN 5 WHEN 'June' THEN 6
    WHEN 'July' THEN 7 WHEN 'August' THEN 8 WHEN 'September' THEN 9
    WHEN 'October' THEN 10 WHEN 'November' THEN 11 WHEN 'December' THEN 12
    ELSE 13 END`;

  res.json({
    kpis,
    trend: all(
      db,
      `SELECT year, month, SUM(revenue) AS revenue, SUM(profit) AS profit
       FROM sales ${sql}
       GROUP BY year, month
       ORDER BY year, ${monthOrder}`,
      params
    ),
    categories: all(
      db,
      `SELECT product_category AS name, SUM(revenue) AS revenue, SUM(profit) AS profit
       FROM sales ${sql}
       GROUP BY product_category
       ORDER BY revenue DESC`,
      params
    ),
    countries: all(
      db,
      `SELECT country AS name, SUM(revenue) AS revenue, SUM(profit) AS profit
       FROM sales ${sql}
       GROUP BY country
       ORDER BY revenue DESC`,
      params
    ),
    products: all(
      db,
      `SELECT product AS name, SUM(order_quantity) AS units, SUM(revenue) AS revenue, SUM(profit) AS profit
       FROM sales ${sql}
       GROUP BY product
       ORDER BY revenue DESC
       LIMIT 10`,
      params
    ),
    ages: all(
      db,
      `SELECT age_group AS name, SUM(revenue) AS revenue
       FROM sales ${sql}
       GROUP BY age_group
       ORDER BY revenue DESC`,
      params
    ),
  });
});

const server = app.listen(PORT, () => {
  console.log(`Sales dashboard: http://localhost:${PORT}`);
});
server.on("error", (err) => {
  console.error(err);
  process.exit(1);
});
process.on("uncaughtException", (err) => {
  console.error(err);
  process.exit(1);
});
