import logging
from typing import Dict, Any, List, Optional, Tuple, Set
from app.services.llama_service import LlamaService
from app.services.sql_service import get_sql_service
import re
from datetime import datetime

logger = logging.getLogger(__name__)

class TextToSQLService:
    def __init__(self):
        self.llama_service = LlamaService
        self.sql_service = get_sql_service()
        self._year_bounds: Optional[Tuple[int, int]] = None  # (min_year, max_year)

        # Authoritative schema used by the prompt
        self.schema = """
        Table: supply_records
        Columns:
        - TransactionID (varchar): Unique transaction identifier
        - FacilityID (varchar): Hospital/facility identifier  
        - FacilityType (varchar): Type of healthcare facility
        - Region (varchar): Geographic region
        - BedSize (int): Number of beds in facility
        - Month (int): Month of transaction (1-12)
        - Year (int): Year of transaction
        - LoadDate (datetime): Data load timestamp
        - Vendor (varchar): Supplier/vendor name
        - VendorID (varchar): Vendor identifier
        - Manufacturer (varchar): Product manufacturer
        - ManufacturerID (varchar): Manufacturer identifier
        - ManufacturerCatalogNum (varchar): Manufacturer catalog number
        - ItemDesc (varchar): Item description/name
        - Quantity (decimal): Quantity purchased
        - PricePaid (decimal): Unit price paid
        - TotalSpend (decimal): Total amount spent (Quantity * PricePaid)
        """

    # ---------------------------- public entry ----------------------------

    def analyze_supply_chain_query(self, user_question: str) -> Dict[str, Any]:
        """Generate SQL, run it, and return a business-facing answer."""
        try:
            q = (user_question or "").strip()
            logger.info(f"Analyzing query: {q}")

            # 0) Super-short greeting? reply immediately (your #1)
            if self._is_greeting(q):
                return {
                    "success": True,
                    "insights": "Hi there! How can I help you analyze your procurement data today?",
                    "data_summary": {"total_records": 0},
                    "recommendations": ["Ask about specific vendors", "Review spending patterns", "Analyze top purchases"],
                    "result_count": 0,
                    "sql_query": None
                }

            # 1) Do we have data at all?
            if not self._has_data():
                return self._no_data_response()

            # 2) Guard against asking for years we don't have (your #2)
            asked_years = self._extract_explicit_years(q)
            if asked_years:
                min_y, max_y = self._get_year_bounds()
                out_of_range = sorted([y for y in asked_years if y < min_y or y > max_y])
                if out_of_range:
                    return {
                        "success": True,
                        "insights": f"No data for year(s) {', '.join(map(str, out_of_range))}. "
                                    f"Available years range from {min_y} to {max_y}.",
                        "data_summary": {"total_records": 0},
                        "recommendations": ["Try a year within the available range",
                                            "Ask for a monthly/quarterly breakdown",
                                            "Review spending trends"],
                        "result_count": 0,
                        "sql_query": None
                    }

            # 3) Generate SQL via LLM
            sql_query = self._generate_sql(q)
            if not sql_query:
                return self._error_response("Could not generate SQL query")

            logger.info(f"Generated SQL: {sql_query}")

            # 4) Execute SQL
            try:
                results = self.sql_service.query_items(sql_query)
                logger.info(f"SQL returned {len(results)} results")
                if results:
                    logger.info(f"First result sample: {results[0]}")
            except Exception as sql_error:
                logger.error(f"SQL execution failed: {sql_error}")
                return self._error_response(f"Database query failed: {str(sql_error)}")

            # 5) Natural-language answer
            insights = self._create_business_response(q, results, sql_query)

            return {
                "success": True,
                "insights": insights,
                "data_summary": self._summarize_data(results),
                "recommendations": self._get_recommendations(q),
                "result_count": len(results),
                "sql_query": sql_query
            }

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            return self._error_response(str(e))

    # ---------------------------- light helpers ----------------------------

    def _is_greeting(self, text: str) -> bool:
        """Return True for short greetings like 'hi', 'Hi there', 'HELLO', etc."""
        t = (text or "").strip().lower()
        if not t:
            return False
        greeting_words = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}
        # short messages (<= 3 words) that start with a greeting word
        words = t.split()
        if len(words) <= 3:
            for g in greeting_words:
                if t == g or t.startswith(g + " "):
                    return True
        return False

    def _has_data(self) -> bool:
        try:
            result = self.sql_service.query_items("SELECT COUNT(*) as count FROM supply_records")
            return result[0]['count'] > 0 if result else False
        except Exception as e:
            logger.error(f"Data availability check failed: {e}")
            return False

    def _get_year_bounds(self) -> Tuple[int, int]:
        """Query and cache min/max year present in the dataset."""
        if self._year_bounds is not None:
            return self._year_bounds
        try:
            rs = self.sql_service.query_items(
                "SELECT MIN(Year) AS MinYear, MAX(Year) AS MaxYear FROM supply_records WHERE Year IS NOT NULL"
            )
            if rs and rs[0].get("MinYear") is not None and rs[0].get("MaxYear") is not None:
                self._year_bounds = (int(rs[0]["MinYear"]), int(rs[0]["MaxYear"]))
            else:
                # fallback if table is empty for safety
                self._year_bounds = (1900, 2100)
        except Exception as e:
            logger.error(f"Year bounds lookup failed: {e}")
            self._year_bounds = (1900, 2100)
        return self._year_bounds

    def _extract_explicit_years(self, question: str) -> Set[int]:
        """Return set of 4-digit years explicitly mentioned (e.g., 2022, 2024)."""
        years = set()
        for m in re.findall(r'\b(20\d{2})\b', question):
            try:
                years.add(int(m))
            except ValueError:
                pass
        return years

    # ---------- Helper: detect "Top N" ----------
    def _extract_top_n(self, question: str, default_n: int = 100) -> int:
        q = question.lower()
        m = re.search(r'\btop\s+(\d{1,4})\b', q) or \
            re.search(r'\bfirst\s+(\d{1,4})\b', q) or \
            re.search(r'\b(?:show|list|return|give)\s+(\d{1,4})\b', q)
        if m:
            try:
                n = int(m.group(1))
                if n > 0:
                    return min(n, 1000)
            except ValueError:
                pass
        return default_n

    # ---------------------------- SQL generation ----------------------------

    def _generate_sql(self, question: str) -> Optional[str]:
        """LLM prompt covering counts, DISTINCT lists, aggregates, dates, and safety."""
        requested_top_n = self._extract_top_n(question, default_n=100)

        prompt = f"""
You are a senior T-SQL engineer. Convert the user's question into a **single safe** SQL Server SELECT
over the table `supply_records`. Use ONLY columns in the schema below. Do **not** invent columns.

SCHEMA (authoritative):
{self.schema}

NATURAL LANGUAGE → COLUMN MAPPING (use these exact columns):
- "product", "item", "sku", "description"   → ItemDesc
- "supplier", "company", "vendor name"      → Vendor
- "spend", "cost", "amount", "total cost"   → TotalSpend
- "qty", "how many", "units"                → Quantity
- "price", "unit price"                     → PricePaid
- "hospital", "facility"                    → FacilityID
- "region"                                  → Region
- Use Year (int) and Month (1–12) for date filters (ignore LoadDate unless explicitly asked).

DATE LOGIC:
- "last year" → WHERE Year = YEAR(GETDATE()) - 1
- "this year" → WHERE Year = YEAR(GETDATE())
- "last month" →
    WHERE Year  = CASE WHEN MONTH(GETDATE())=1 THEN YEAR(GETDATE())-1 ELSE YEAR(GETDATE()) END
      AND Month = CASE WHEN MONTH(GETDATE())=1 THEN 12 ELSE MONTH(GETDATE())-1 END
- Month names & abbreviations → January/Jan=1, February/Feb=2, … December/Dec=12 (filter with Month = N)
- Quarters → Q1: (1,2,3), Q2: (4,5,6), Q3: (7,8,9), Q4: (10,11,12)
- Explicit (e.g., July 2024) → WHERE Year = 2024 AND Month = 7

OUTPUT RULES (critical):
1) Return **ONLY** a single SELECT statement. No comments/backticks/explanations.
2) Use exact column names. Prefer explicit column lists; avoid SELECT * unless user asks for "all columns".
3) For "Top/first/list N" rows, use TOP {requested_top_n}.
4) Aggregations must include GROUP BY for non-aggregated columns.
5) NEVER use DDL/DML (DROP/DELETE/TRUNCATE/ALTER/CREATE/INSERT/UPDATE).
6) Fuzzy item search must be case/punctuation robust: compare **LOWER(ItemDesc)** and match both singular and plural roots.
   Example for "syringe/SYRINGES.":  LOWER(ItemDesc) LIKE '%syringe%' OR LOWER(ItemDesc) LIKE '%syringes%'.
7) Single aggregate aliases (wrap with COALESCE to avoid NULL):
   - COUNT(*)                      → AS TransactionCount
   - SUM(Quantity)                 → AS TotalQuantity
   - SUM(TotalSpend)               → AS TotalSpend
   - AVG(PricePaid)                → AS AverageUnitPrice
8) “What values exist / list all / unique …” → SELECT DISTINCT <column> ORDER BY <column>.
9) “how many transactions …” (no grouping) → SELECT COUNT(*) AS TransactionCount FROM supply_records [filters].

GOOD EXAMPLES:
-- 1) Exact transaction:
Q: transaction 123 details
A: SELECT TransactionID, Vendor, VendorID, ItemDesc, Quantity, PricePaid, TotalSpend, FacilityID, Month, Year
   FROM supply_records
   WHERE TransactionID = '123';

-- 2) Top products by spend:
Q: top 5 products by total spend
A: SELECT TOP 5 ItemDesc, SUM(TotalSpend) AS TotalSpend, COUNT(*) AS TransactionCount
   FROM supply_records
   GROUP BY ItemDesc
   ORDER BY TotalSpend DESC;

-- 3) Highest-spend vendors last month:
Q: which vendors had the highest spend last month
A: SELECT Vendor, SUM(TotalSpend) AS TotalSpend, COUNT(*) AS TransactionCount
   FROM supply_records
   WHERE (Year = CASE WHEN MONTH(GETDATE())=1 THEN YEAR(GETDATE())-1 ELSE YEAR(GETDATE()) END)
     AND (Month = CASE WHEN MONTH(GETDATE())=1 THEN 12 ELSE MONTH(GETDATE())-1 END)
   GROUP BY Vendor
   ORDER BY TotalSpend DESC;

-- 3b) COUNT last month (explicitly for reliability):
Q: how many transactions last month
A: SELECT COUNT(*) AS TransactionCount
   FROM supply_records
   WHERE (Year = CASE WHEN MONTH(GETDATE())=1 THEN YEAR(GETDATE())-1 ELSE YEAR(GETDATE()) END)
     AND (Month = CASE WHEN MONTH(GETDATE())=1 THEN 12 ELSE MONTH(GETDATE())-1 END);

-- 4) Show transactions from last year:
Q: show all transactions from last year
A: SELECT TOP {requested_top_n} TransactionID, Vendor, VendorID, ItemDesc, Quantity, PricePaid, TotalSpend, FacilityID, Month, Year
   FROM supply_records
   WHERE Year = YEAR(GETDATE()) - 1
   ORDER BY Month DESC, TotalSpend DESC;

-- 5) Fuzzy item + quantity (case & punctuation tolerant):
Q: how many SYRINGES. were purchased
A: SELECT COALESCE(SUM(Quantity),0) AS TotalQuantity
   FROM supply_records
   WHERE LOWER(ItemDesc) LIKE '%syringe%' OR LOWER(ItemDesc) LIKE '%syringes%';

Q: how many gloves were purchased
A: SELECT COALESCE(SUM(Quantity),0) AS TotalQuantity
   FROM supply_records
   WHERE LOWER(ItemDesc) LIKE '%glove%' OR LOWER(ItemDesc) LIKE '%gloves%';

-- 6) Average unit price (your #3):
Q: what's the average unit price for all items
A: SELECT COALESCE(AVG(PricePaid),0) AS AverageUnitPrice
   FROM supply_records;

-- 7) DISTINCT listing:
Q: what regions are included in the data
A: SELECT DISTINCT Region
   FROM supply_records
   WHERE Region IS NOT NULL
   ORDER BY Region;

-- 8) TOTAL COUNT (by year and by month name):
Q: how many transactions in 2022
A: SELECT COUNT(*) AS TransactionCount
   FROM supply_records
   WHERE Year = 2022;

Q: how many transactions in September 2022
A: SELECT COUNT(*) AS TransactionCount
   FROM supply_records
   WHERE Year = 2022 AND Month = 9;

USER QUESTION:
{question}

RETURN ONLY THE SQL:
        """

        try:
            sql = self.llama_service.query(prompt, max_tokens=240, temperature=0.05)
            cleaned_sql = self._clean_sql(sql)
            logger.info(f"Generated SQL: {cleaned_sql}")
            return cleaned_sql
        except Exception as e:
            logger.error(f"SQL generation failed: {e}")
            return None

    def _clean_sql(self, query: str) -> str:
        if not query:
            raise ValueError("Empty SQL query")
        # Remove markdown fences
        query = re.sub(r'```sql\s*|\s*```', '', query).strip()
        # Remove trailing semicolon
        query = query.rstrip(';').strip()
        # Normalize misordered TOP
        query = re.sub(r'SELECT\s+(.+?)\s+TOP\s+(\d+)', r'SELECT TOP \2 \1', query, flags=re.IGNORECASE)
        # Basic safety
        dangerous = ['DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'CREATE', 'INSERT', 'UPDATE']
        if any(word in query.upper() for word in dangerous):
            raise ValueError("Unsafe SQL operation detected")
        if not query.upper().startswith('SELECT'):
            raise ValueError("Query must start with SELECT")
        return query

    # ---------------------------- response building ----------------------------

    def _build_preview(self, results: List[Dict], max_rows: int = 8) -> str:
        if not results:
            return ""
        dim_candidates = ["Region", "Vendor", "ItemDesc", "FacilityType", "FacilityID", "Manufacturer", "Year", "Month"]
        met_candidates = ["TotalSpend", "TotalQuantity", "TransactionCount", "Quantity", "PricePaid", "AverageUnitPrice"]
        present = set(results[0].keys())

        dims = [c for c in dim_candidates if c in present]
        mets = [c for c in met_candidates if c in present]
        cols = (dims[:2] + mets) or list(present)[:4]

        lines = [", ".join(cols)]
        for r in results[:max_rows]:
            vals = []
            for c in cols:
                v = r.get(c)
                if isinstance(v, (int, float)):
                    if "Spend" in c or "Price" in c or "Average" in c or "Avg" in c:
                        vals.append(f"${float(v):,.2f}")
                    else:
                        fv = float(v)
                        vals.append(str(int(fv)) if fv.is_integer() else str(fv))
                else:
                    vals.append("" if v is None else str(v))
            lines.append(", ".join(vals))
        return "\n".join(lines)

    def _create_business_response(self, question: str, results: List[Dict], sql_query: str) -> str:
        """Use only retrieved data; concise (<100 words)."""
        if not results:
            return "No relevant data found for your question. Try asking about specific vendors, items, or facilities in your uploaded data."

        # Greeting already handled earlier, but keep a light guard:
        if self._is_greeting(question):
            return "Hi there! How can I help you analyze your procurement data today?"

        context = self._format_results_safe(results, question)
        preview = self._build_preview(results)
        available_columns = list(results[0].keys()) if results else []

        prompt = f"""
        You are EARL, a helpful supply chain AI assistant for hospital managers.

        User Question: {question}

        Retrieved Data Summary:
        {context}

        Data Preview (first rows):
        {preview}

        Available Data Fields: {available_columns}

        RULES:
        - Use only information visible in the Data Preview / Retrieved Data Summary.
        - If the summary contains a DISTINCT list like "Regions: …", restate it concisely.
        - If the preview shows numeric columns (e.g., TotalSpend, TotalQuantity, TransactionCount, AverageUnitPrice), quote the numbers exactly.
        - Keep the response under 100 words, clear and specific.
        """
        try:
            return self.llama_service.query(prompt, max_tokens=180, temperature=0.1).strip()
        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            return f"I found the data but had trouble formatting the response. Here's what I found: {context}"

    # ---------------------------- summarizer ----------------------------

    def _format_results_safe(self, results: List[Dict], question: str) -> str:
        if not results:
            return "No data found"

        def safe_get(record: Dict, key: str, default: str = "Not available") -> str:
            v = record.get(key)
            if v is None or v == '' or str(v).lower() == 'none':
                return default
            return str(v)

        def safe_float(record: Dict, key: str, default: float = 0.0) -> float:
            v = record.get(key)
            if v is None or v == '' or str(v).lower() == 'none':
                return default
            try:
                return float(v)
            except (ValueError, TypeError):
                return default

        # 0) Single-value numeric results (TotalQuantity / TotalSpend / TransactionCount / AverageUnitPrice)
        if len(results) == 1:
            r = results[0]
            if "AverageUnitPrice" in r and r["AverageUnitPrice"] is not None:
                try:
                    val = float(r["AverageUnitPrice"])
                    return f"Average unit price: ${val:,.2f}"
                except Exception:
                    pass
            if "TotalQuantity" in r and r["TotalQuantity"] is not None:
                v = float(r["TotalQuantity"])
                return f"Total quantity: {int(v) if v.is_integer() else v}"
            if "TransactionCount" in r and r["TransactionCount"] is not None:
                v = float(r["TransactionCount"])
                return f"Total transactions: {int(v) if v.is_integer() else v}"
            if "TotalSpend" in r and r["TotalSpend"] is not None:
                v = float(r["TotalSpend"])
                return f"Total spend: ${v:,.2f}"
            # Generic single-number fallback
            if len(r.keys()) == 1:
                k = next(iter(r.keys()))
                try:
                    v = float(r[k])
                    if "avg" in k.lower() or "average" in k.lower() or "price" in k.lower() or "spend" in k.lower():
                        return f"{k}: ${v:,.2f}"
                    return f"{k}: {int(v) if v.is_integer() else v}"
                except Exception:
                    pass

        # 1) Single transaction detail
        if len(results) == 1 and 'transaction' in question.lower():
            r = results[0]
            parts = []
            if 'TransactionID' in r: parts.append(f"Transaction {safe_get(r, 'TransactionID')}")
            if 'ItemDesc' in r:      parts.append(f"Item: {safe_get(r, 'ItemDesc')}")
            if 'Vendor' in r:        parts.append(f"Vendor: {safe_get(r, 'Vendor')}")
            if 'Quantity' in r:      parts.append(f"Quantity: {safe_get(r, 'Quantity', 'Not available')}")
            if 'PricePaid' in r:
                price = safe_float(r, 'PricePaid')
                parts.append(f"Unit Price: ${price:,.2f}" if price > 0 else "Unit Price: Not available")
            if 'TotalSpend' in r:
                total = safe_float(r, 'TotalSpend')
                parts.append(f"Total: ${total:,.2f}" if total > 0 else "Total: Not available")
            return " | ".join(parts)

        # 2) DISTINCT listings (e.g., SELECT DISTINCT Region)
        present_keys = set(results[0].keys())
        known_dims = ["Region", "Vendor", "ItemDesc", "FacilityType", "FacilityID", "Manufacturer"]
        metric_like = {"TotalSpend", "TotalQuantity", "TransactionCount", "Quantity", "PricePaid", "AverageUnitPrice"}

        distinct_dim = None
        for dim in known_dims:
            if dim in present_keys and not any(m in present_keys for m in metric_like):
                distinct_dim = dim
                break
        if distinct_dim:
            seen, values = set(), []
            for r in results:
                val = safe_get(r, distinct_dim, 'Unknown')
                if val not in seen:
                    seen.add(val)
                    values.append(val)
            if values:
                label = {"ItemDesc": "products", "FacilityType": "facility types"}.get(distinct_dim, distinct_dim.lower() + "s")
                return f"{label.capitalize()}: " + ", ".join(values)

        # 3) Aggregate / multi-row summary
        candidate_dims = ["Region", "Vendor", "ItemDesc", "FacilityID", "FacilityType", "Manufacturer", "Year", "Month"]
        group_key = next((k for k in candidate_dims if k in present_keys), None)

        def row_spend(r: Dict) -> float:
            ts = r.get('TotalSpend', None)
            try:
                ts_val = float(ts) if ts is not None and str(ts).lower() != 'none' and str(ts) != '' else None
            except (ValueError, TypeError):
                ts_val = None
            if ts_val is not None and ts_val > 0:
                return ts_val
            q = safe_float(r, 'Quantity', 0.0)
            p = safe_float(r, 'PricePaid', 0.0)
            return q * p if (q > 0 and p > 0) else 0.0

        # Pure COUNT(*) results fallback
        if len(results) == 1 and ('TransactionCount' in results[0] or 'COUNT' in ''.join(results[0].keys()).upper()):
            count_val = results[0].get('TransactionCount')
            if count_val is None:
                for v in results[0].values():
                    try:
                        count_val = int(v)
                        break
                    except (ValueError, TypeError):
                        continue
            return f"Total transactions: {count_val}"

        total_spend = sum(row_spend(r) for r in results)

        distinct_count = 0
        if group_key:
            distinct_count = len(set(safe_get(r, group_key, 'Unknown') for r in results if group_key in r))

        context = f"{len(results)} records found"
        if total_spend > 0:
            context += f", ${total_spend:,.2f} total spend"

        if group_key and distinct_count > 0:
            pretty = {
                "Vendor": "vendors",
                "Region": "regions",
                "ItemDesc": "products",
                "FacilityID": "facilities",
                "FacilityType": "facility types",
                "Manufacturer": "manufacturers",
                "Year": "years",
                "Month": "months",
            }.get(group_key, group_key.lower() + "s")
            context += f", {distinct_count} {pretty}"

        # Top group by spend
        if group_key and ('TotalSpend' in present_keys or any('TotalSpend' in r for r in results)):
            totals = {}
            for r in results:
                if group_key in r:
                    key = safe_get(r, group_key, 'Unknown')
                    totals[key] = totals.get(key, 0.0) + row_spend(r)
            if totals:
                top_key, top_val = max(totals.items(), key=lambda x: x[1])
                if top_val > 0:
                    context += f" | Top {group_key.lower()}: {top_key} (${top_val:,.2f})"

        return context

    # ---------------------------- light summaries ----------------------------

    def _summarize_data(self, results: List[Dict]) -> Dict[str, Any]:
        if not results:
            return {"total_records": 0}
        def safe_float(record: Dict, key: str) -> float:
            value = record.get(key, 0)
            if value is None or value == '' or str(value).lower() == 'none':
                return 0.0
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        total_spend = sum(safe_float(r, 'TotalSpend') for r in results)
        return {
            "total_records": len(results),
            "total_spend": total_spend,
            "average_spend": total_spend / len(results) if len(results) > 0 else 0,
            "unique_vendors": len(set(r.get('Vendor', '') for r in results if r.get('Vendor'))),
            "unique_items": len(set(r.get('ItemDesc', '') for r in results if r.get('ItemDesc')))
        }

    def _get_recommendations(self, question: str) -> List[str]:
        q = question.lower()
        if 'vendor' in q:
            return ["Compare vendor pricing", "Analyze vendor performance", "Find alternative suppliers"]
        elif 'cost' in q or 'spend' in q:
            return ["Identify cost savings", "Review spending trends", "Compare departmental costs"]
        elif 'transaction' in q or 'count' in q:
            return ["View transaction details", "Find similar purchases", "Check vendor history"]
        else:
            return ["Ask about specific vendors", "Review spending patterns", "Analyze top purchases"]

    # ---------------------------- generic error/empty ----------------------------

    def _no_data_response(self) -> Dict[str, Any]:
        return {
            "success": False,
            "insights": "No supply chain data uploaded yet. Please upload a CSV file to get started.",
            "data_summary": {"total_records": 0},
            "recommendations": ["Upload CSV file", "Check file format", "Try sample data"],
            "result_count": 0
        }

    def _error_response(self, error: str) -> Dict[str, Any]:
        return {
            "success": False,
            "insights": "I'm having trouble analyzing your request. Please try rephrasing your question.",
            "data_summary": {"total_records": 0},
            "recommendations": ["Try different keywords", "Ask about specific items", "Check data upload"],
            "result_count": 0,
            "error": error
        }

# Singleton instance
text_to_sql_service = TextToSQLService()

def get_text_to_sql_service() -> TextToSQLService:
    return text_to_sql_service
