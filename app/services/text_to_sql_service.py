import logging
from typing import Dict, Any, List, Optional, Tuple
from app.services.llama_service import LlamaService
from app.services.sql_service import get_sql_service
import re

logger = logging.getLogger(__name__)

class TextToSQLService:
    def __init__(self):
        # Properly instantiate services
        self.llama_service = LlamaService()
        self.sql_service = get_sql_service()

        # Authoritative schema (prompt-facing)
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

        # Pre-compiled patterns
        self._compile_patterns()

    def _compile_patterns(self):
        self.dangerous_patterns = [
            re.compile(r'\bDROP\b', re.IGNORECASE),
            re.compile(r'\bDELETE\b', re.IGNORECASE),
            re.compile(r'\bTRUNCATE\b', re.IGNORECASE),
            re.compile(r'\bALTER\b', re.IGNORECASE),
            re.compile(r'\bCREATE\b', re.IGNORECASE),
            re.compile(r'\bINSERT\b', re.IGNORECASE),
            re.compile(r'\bUPDATE\b', re.IGNORECASE),
            re.compile(r'\bEXEC\b', re.IGNORECASE),
        ]
        self.year_pattern = re.compile(r'20\d{2}')
        self.top_pattern = re.compile(r'top\s+(\d+)', re.IGNORECASE)
        self.bottom_pattern = re.compile(r'bottom\s+(\d+)', re.IGNORECASE)
        self.transaction_pattern = re.compile(r'transaction\s+(\d+)', re.IGNORECASE)

    # --- Intent helpers -----------------------------------------------------

    def _is_top1_intent(self, q: str) -> bool:
        ql = q.lower()
        superlatives = [
            'who is the top', 'who is top', 'who is #1', 'who is number 1',
            'highest', 'most', 'largest', 'leading', 'biggest', 'rank 1', '#1', 'number one'
        ]
        if not (('vendor' in ql) or ('manufacturer' in ql)):
            return False
        return any(word in ql for word in superlatives) or ql.strip().startswith('top ')

    def _is_top_list_intent(self, q: str) -> Optional[Tuple[str, int]]:
        """Returns ('Vendor'|'Manufacturer', n) if asking for top-N list, else None."""
        ql = q.lower()
        m = self.top_pattern.search(ql)
        if not m:
            return None
        n = int(m.group(1))
        if 'vendor' in ql:
            return ('Vendor', n)
        if 'manufacturer' in ql:
            return ('Manufacturer', n)
        return None

    # --- Public entry -------------------------------------------------------

    def analyze_supply_chain_query(self, user_question: str) -> Dict[str, Any]:
        try:
            q = (user_question or "").strip()
            logger.info(f"Starting analysis for query: '{q}'")

            if self._is_greeting(q):
                logger.info("Detected greeting")
                return self._greeting_response()

            logger.info("Checking data availability...")
            if not self._has_data():
                logger.warning("No data found")
                return self._no_data_response()
            logger.info("Data available")

            logger.info("Generating SQL...")
            sql_query = self._generate_sql_with_fallback(q)
            if not sql_query:
                logger.error("Failed to generate SQL")
                return self._error_response("Could not generate SQL query")
            logger.info(f"Successfully generated SQL: {sql_query}")

            logger.info("Executing SQL query...")
            try:
                results = self.sql_service.query_items(sql_query)
                logger.info(f"SQL executed, {len(results)} results")
                if results:
                    logger.info(f"Sample result: {results[0]}")
            except Exception as sql_error:
                logger.error(f"SQL execution failed: {sql_error}")
                return self._error_response(f"Database query failed: {str(sql_error)}")

            # Deterministic, concise answers for top lists and top-1
            top_list = self._is_top_list_intent(q)
            if top_list and results:
                kind, n = top_list  # 'Vendor' or 'Manufacturer'
                insights = self._format_top_n_response(kind, results, n)
                return {
                    "success": True,
                    "insights": insights,
                    "data_summary": self._summarize_data(results),
                    "recommendations": [],  # keep clean for list requests
                    "result_count": len(results),
                    "sql_query": sql_query,
                }

            if self._is_top1_intent(q) and results:
                r0 = results[0]
                name_key = 'Vendor' if 'Vendor' in r0 else ('Manufacturer' if 'Manufacturer' in r0 else None)
                if name_key and 'TotalSpend' in r0:
                    amount = float(r0.get('TotalSpend') or 0.0)
                    name = r0.get(name_key, 'Unknown')
                    insights = f"- {name} — ${amount:,.2f}"
                    return {
                        "success": True,
                        "insights": insights,
                        "data_summary": self._summarize_data(results),
                        "recommendations": [],
                        "result_count": len(results),
                        "sql_query": sql_query,
                    }

            # Otherwise, use LLM natural response (concise bullets)
            logger.info("Generating natural language response via LLM...")
            insights = self._create_natural_response(q, results)
            logger.info(f"Generated response: '{insights[:100]}...'")

            return {
                "success": True,
                "insights": insights,
                "data_summary": self._summarize_data(results),
                "recommendations": self._get_contextual_recommendations(q, results),
                "result_count": len(results),
                "sql_query": sql_query,
            }

        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return self._error_response(str(e))

    # --- SQL generation -----------------------------------------------------

    def _generate_sql_with_fallback(self, question: str) -> Optional[str]:
        logger.info(f"Starting SQL generation for question: '{question}'")
        try:
            sql_query = self._generate_sql_with_llm(question)
            if sql_query:
                logger.info(f"LLM SQL ok: {sql_query}")
                return sql_query
            else:
                logger.warning("LLM did not return valid SQL")
        except Exception as llm_error:
            logger.warning(f"LLM failed ({llm_error}), trying fallback...")
        fallback_sql = self._generate_fallback_sql(question)
        if fallback_sql:
            logger.info(f"Fallback SQL: {fallback_sql}")
            return fallback_sql
        logger.error("Both LLM and fallback SQL generation failed")
        return None

    def _generate_sql_with_llm(self, question: str) -> Optional[str]:
        prompt = f"""
You are an expert SQL analyst specializing in supply chain and procurement data. Convert this natural language question into a SQL Server query for the supply_records table.

SCHEMA:
{self.schema}

ADVANCED GUIDELINES:
- Use ONLY columns that exist in the schema above
- Return a single SELECT statement only
- For text searches, use LIKE with wildcards (%) and be case-insensitive
- For dates: Year (int 1-9999), Month (int 1-12)
- For aggregations: SUM() for totals, COUNT() for counts, AVG() for averages
- For rankings: ORDER BY with TOP N or OFFSET/FETCH
- For grouping: GROUP BY when showing breakdowns by categories
- For comparisons: Include multiple metrics (spend, count, averages)
- Handle NULL values with WHERE column IS NOT NULL when appropriate
- For trends over time: GROUP BY Year, Month or just Year

FLEXIBLE MAPPINGS:
- "vendors/suppliers/companies" → Vendor
- "items/products/materials/goods" → ItemDesc
- "facilities/hospitals/sites/locations" → FacilityID
- "spend/cost/amount/price/money" → TotalSpend
- "purchases/transactions/orders" → COUNT(*)
- "regions/areas/territories" → Region
- "manufacturers/makers" → Manufacturer

EXAMPLES:
- Which vendors spend the most? → SELECT Vendor, SUM(TotalSpend) AS TotalSpend FROM supply_records WHERE Vendor IS NOT NULL GROUP BY Vendor ORDER BY TotalSpend DESC
- Average spend by region → SELECT Region, AVG(TotalSpend) AS AverageSpend FROM supply_records WHERE Region IS NOT NULL GROUP BY Region ORDER BY AverageSpend DESC
- Count of items → SELECT COUNT(DISTINCT ItemDesc) AS ItemCount FROM supply_records WHERE ItemDesc IS NOT NULL
- Monthly trends in 2022 → SELECT Month, SUM(TotalSpend) AS TotalSpend FROM supply_records WHERE Year = 2022 GROUP BY Month ORDER BY Month

QUESTION: {question}

SQL:"""
        logger.info("Calling LlamaService.query()...")
        sql = self.llama_service.query(prompt, max_tokens=200, temperature=0.1)
        logger.info(f"LLM raw SQL: '{sql}'")
        if sql:
            cleaned_sql = self._clean_and_validate_sql(sql)
            logger.info(f"Cleaned SQL: '{cleaned_sql}'")
            return cleaned_sql
        return None

    def _generate_fallback_sql(self, question: str) -> Optional[str]:
        q = question.lower().strip()
        sql_generators = [
            self._generate_list_queries,
            self._generate_aggregate_queries,
            self._generate_count_queries,
            self._generate_ranking_queries,
            self._generate_comparison_queries,
            self._generate_trend_queries,
            self._generate_detail_queries,
            self._generate_generic_queries,
        ]
        for generator in sql_generators:
            sql = generator(q)
            if sql:
                return sql
        return None

    # --- Query category generators -----------------------------------------

    def _generate_list_queries(self, q: str) -> Optional[str]:
        if not any(word in q for word in ['list', 'show', 'display', 'get', 'all']):
            return None

        if 'vendor' in q:
            if any(word in q for word in ['unique', 'distinct', 'different']):
                return "SELECT DISTINCT Vendor FROM supply_records WHERE Vendor IS NOT NULL ORDER BY Vendor"
            return ("SELECT Vendor, SUM(TotalSpend) AS TotalSpend, COUNT(*) AS TransactionCount "
                    "FROM supply_records WHERE Vendor IS NOT NULL "
                    "GROUP BY Vendor ORDER BY TotalSpend DESC")

        if 'manufacturer' in q:
            if any(word in q for word in ['unique', 'distinct', 'different']):
                return "SELECT DISTINCT Manufacturer FROM supply_records WHERE Manufacturer IS NOT NULL ORDER BY Manufacturer"
            return ("SELECT Manufacturer, SUM(TotalSpend) AS TotalSpend, COUNT(*) AS TransactionCount "
                    "FROM supply_records WHERE Manufacturer IS NOT NULL "
                    "GROUP BY Manufacturer ORDER BY TotalSpend DESC")

        if any(word in q for word in ['item', 'product']):
            if any(word in q for word in ['unique', 'distinct', 'different']):
                return "SELECT DISTINCT ItemDesc FROM supply_records WHERE ItemDesc IS NOT NULL ORDER BY ItemDesc"
            return ("SELECT ItemDesc, SUM(TotalSpend) AS TotalSpend, COUNT(*) AS TransactionCount "
                    "FROM supply_records WHERE ItemDesc IS NOT NULL "
                    "GROUP BY ItemDesc ORDER BY TotalSpend DESC")

        if any(word in q for word in ['facility', 'hospital']):
            return ("SELECT FacilityID, FacilityType, Region, COUNT(*) AS TransactionCount, SUM(TotalSpend) AS TotalSpend "
                    "FROM supply_records WHERE FacilityID IS NOT NULL "
                    "GROUP BY FacilityID, FacilityType, Region ORDER BY TotalSpend DESC")

        if 'region' in q:
            return ("SELECT Region, COUNT(*) AS TransactionCount, SUM(TotalSpend) AS TotalSpend "
                    "FROM supply_records WHERE Region IS NOT NULL "
                    "GROUP BY Region ORDER BY TotalSpend DESC")

        return None

    def _generate_aggregate_queries(self, q: str) -> Optional[str]:
        if any(word in q for word in ['total', 'sum']):
            if any(word in q for word in ['spend', 'cost', 'amount']):
                return self._generate_spend_queries(q)

        if any(word in q for word in ['average', 'avg', 'mean']):
            if any(word in q for word in ['spend', 'cost', 'price']):
                if 'vendor' in q:
                    return ("SELECT Vendor, AVG(TotalSpend) AS AverageSpend "
                            "FROM supply_records WHERE Vendor IS NOT NULL "
                            "GROUP BY Vendor ORDER BY AverageSpend DESC")
                if 'manufacturer' in q:
                    return ("SELECT Manufacturer, AVG(TotalSpend) AS AverageSpend "
                            "FROM supply_records WHERE Manufacturer IS NOT NULL "
                            "GROUP BY Manufacturer ORDER BY AverageSpend DESC")
                return "SELECT AVG(TotalSpend) AS AverageSpend FROM supply_records"
        return None

    def _generate_spend_queries(self, q: str) -> Optional[str]:
        region_patterns = {
            'south atlantic': "SELECT SUM(TotalSpend) AS TotalSpend FROM supply_records WHERE Region LIKE '%South Atlantic%'",
            'north atlantic': "SELECT SUM(TotalSpend) AS TotalSpend FROM supply_records WHERE Region LIKE '%North Atlantic%'",
            'mountain': "SELECT SUM(TotalSpend) AS TotalSpend FROM supply_records WHERE Region LIKE '%Mountain%'",
            'pacific': "SELECT SUM(TotalSpend) AS TotalSpend FROM supply_records WHERE Region LIKE '%Pacific%'",
        }
        for region_name, sql in region_patterns.items():
            if region_name in q:
                return sql

        if 'region' in q and not any(region in q for region in region_patterns.keys()):
            return ("SELECT Region, SUM(TotalSpend) AS TotalSpend "
                    "FROM supply_records WHERE Region IS NOT NULL "
                    "GROUP BY Region ORDER BY TotalSpend DESC")

        year_match = self.year_pattern.search(q)
        if year_match:
            year = year_match.group()
            month_map = {
                'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
                'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
            }
            for month_name, month_num in month_map.items():
                if month_name in q or month_name[:3] in q:
                    return f"SELECT SUM(TotalSpend) AS TotalSpend FROM supply_records WHERE Month = {month_num} AND Year = {year}"
            return f"SELECT SUM(TotalSpend) AS TotalSpend FROM supply_records WHERE Year = {year}"

        if 'manufacturer' in q:
            if self._is_top1_intent(q):
                return ("SELECT TOP 1 Manufacturer, SUM(TotalSpend) AS TotalSpend "
                        "FROM supply_records WHERE Manufacturer IS NOT NULL "
                        "GROUP BY Manufacturer ORDER BY TotalSpend DESC")
            return ("SELECT Manufacturer, SUM(TotalSpend) AS TotalSpend "
                    "FROM supply_records WHERE Manufacturer IS NOT NULL "
                    "GROUP BY Manufacturer ORDER BY TotalSpend DESC")

        if 'vendor' in q:
            if self._is_top1_intent(q):
                return ("SELECT TOP 1 Vendor, SUM(TotalSpend) AS TotalSpend "
                        "FROM supply_records WHERE Vendor IS NOT NULL "
                        "GROUP BY Vendor ORDER BY TotalSpend DESC")
            return ("SELECT Vendor, SUM(TotalSpend) AS TotalSpend "
                    "FROM supply_records WHERE Vendor IS NOT NULL "
                    "GROUP BY Vendor ORDER BY TotalSpend DESC")

        return "SELECT SUM(TotalSpend) AS TotalSpend FROM supply_records"

    def _generate_count_queries(self, q: str) -> Optional[str]:
        if not any(word in q for word in ['count', 'how many', 'number of']):
            return None

        if 'transaction' in q:
            return "SELECT COUNT(*) AS TransactionCount FROM supply_records"
        if 'vendor' in q:
            return "SELECT COUNT(DISTINCT Vendor) AS VendorCount FROM supply_records WHERE Vendor IS NOT NULL"
        if 'manufacturer' in q:
            return "SELECT COUNT(DISTINCT Manufacturer) AS ManufacturerCount FROM supply_records WHERE Manufacturer IS NOT NULL"
        if any(word in q for word in ['item', 'product']):
            return "SELECT COUNT(DISTINCT ItemDesc) AS ItemCount FROM supply_records WHERE ItemDesc IS NOT NULL"
        if 'facility' in q:
            return "SELECT COUNT(DISTINCT FacilityID) AS FacilityCount FROM supply_records WHERE FacilityID IS NOT NULL"
        return None

    def _generate_ranking_queries(self, q: str) -> Optional[str]:
        """Ranking queries using OFFSET/FETCH for top-N."""
        top_match = self.top_pattern.search(q)
        bottom_match = self.bottom_pattern.search(q)

        # If "top" present but no explicit number, default to 1
        if 'top' in q and not top_match:
            n = '1'
            if 'vendor' in q:
                return ("SELECT Vendor, SUM(TotalSpend) AS TotalSpend "
                        "FROM supply_records WHERE Vendor IS NOT NULL "
                        "GROUP BY Vendor ORDER BY TotalSpend DESC "
                        "OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY")
            if 'manufacturer' in q:
                return ("SELECT Manufacturer, SUM(TotalSpend) AS TotalSpend "
                        "FROM supply_records WHERE Manufacturer IS NOT NULL "
                        "GROUP BY Manufacturer ORDER BY TotalSpend DESC "
                        "OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY")

        if top_match:
            n = top_match.group(1)
            if 'vendor' in q:
                return (f"SELECT Vendor, SUM(TotalSpend) AS TotalSpend "
                        f"FROM supply_records WHERE Vendor IS NOT NULL "
                        f"GROUP BY Vendor ORDER BY TotalSpend DESC "
                        f"OFFSET 0 ROWS FETCH NEXT {n} ROWS ONLY")
            if 'manufacturer' in q:
                return (f"SELECT Manufacturer, SUM(TotalSpend) AS TotalSpend "
                        f"FROM supply_records WHERE Manufacturer IS NOT NULL "
                        f"GROUP BY Manufacturer ORDER BY TotalSpend DESC "
                        f"OFFSET 0 ROWS FETCH NEXT {n} ROWS ONLY")
            if any(word in q for word in ['item', 'product']):
                return (f"SELECT ItemDesc, SUM(TotalSpend) AS TotalSpend "
                        f"FROM supply_records WHERE ItemDesc IS NOT NULL "
                        f"GROUP BY ItemDesc ORDER BY TotalSpend DESC "
                        f"OFFSET 0 ROWS FETCH NEXT {n} ROWS ONLY")
            if 'facility' in q:
                return (f"SELECT FacilityID, SUM(TotalSpend) AS TotalSpend "
                        f"FROM supply_records WHERE FacilityID IS NOT NULL "
                        f"GROUP BY FacilityID ORDER BY TotalSpend DESC "
                        f"OFFSET 0 ROWS FETCH NEXT {n} ROWS ONLY")

        if bottom_match:
            n = bottom_match.group(1)
            if 'vendor' in q:
                return (f"SELECT Vendor, SUM(TotalSpend) AS TotalSpend "
                        f"FROM supply_records WHERE Vendor IS NOT NULL "
                        f"GROUP BY Vendor ORDER BY TotalSpend ASC "
                        f"OFFSET 0 ROWS FETCH NEXT {n} ROWS ONLY")
            if 'manufacturer' in q:
                return (f"SELECT Manufacturer, SUM(TotalSpend) AS TotalSpend "
                        f"FROM supply_records WHERE Manufacturer IS NOT NULL "
                        f"GROUP BY Manufacturer ORDER BY TotalSpend ASC "
                        f"OFFSET 0 ROWS FETCH NEXT {n} ROWS ONLY")

        return None

    def _generate_comparison_queries(self, q: str) -> Optional[str]:
        if not any(word in q for word in ['compare', 'comparison', 'vs', 'versus']):
            return None

        if 'vendor' in q:
            return ("SELECT Vendor, SUM(TotalSpend) AS TotalSpend, COUNT(*) AS TransactionCount, AVG(PricePaid) AS AveragePrice "
                    "FROM supply_records WHERE Vendor IS NOT NULL "
                    "GROUP BY Vendor ORDER BY TotalSpend DESC")
        if 'manufacturer' in q:
            return ("SELECT Manufacturer, SUM(TotalSpend) AS TotalSpend, COUNT(*) AS TransactionCount, AVG(PricePaid) AS AveragePrice "
                    "FROM supply_records WHERE Manufacturer IS NOT NULL "
                    "GROUP BY Manufacturer ORDER BY TotalSpend DESC")
        if 'region' in q:
            return ("SELECT Region, SUM(TotalSpend) AS TotalSpend, COUNT(*) AS TransactionCount "
                    "FROM supply_records WHERE Region IS NOT NULL "
                    "GROUP BY Region ORDER BY TotalSpend DESC")
        return None

    def _generate_trend_queries(self, q: str) -> Optional[str]:
        if not any(word in q for word in ['trend', 'over time', 'monthly', 'yearly']):
            return None

        if 'monthly' in q or 'month' in q:
            return ("SELECT Year, Month, SUM(TotalSpend) AS TotalSpend "
                    "FROM supply_records GROUP BY Year, Month ORDER BY Year, Month")
        if 'yearly' in q or 'year' in q:
            return "SELECT Year, SUM(TotalSpend) AS TotalSpend FROM supply_records GROUP BY Year ORDER BY Year"
        return None

    def _generate_detail_queries(self, q: str) -> Optional[str]:
        transaction_match = self.transaction_pattern.search(q)
        if transaction_match:
            return f"SELECT * FROM supply_records WHERE TransactionID = '{transaction_match.group(1)}'"

        if any(word in q for word in ['detail', 'details', 'information', 'info']):
            if 'vendor' in q:
                vendor_match = re.search(r'vendor\s+(["\']?)([^"\']+)\1', q)
                if vendor_match:
                    vendor = vendor_match.group(2)
                    return f"SELECT * FROM supply_records WHERE Vendor LIKE '%{vendor}%'"
            if 'manufacturer' in q:
                manu_match = re.search(r'manufacturer\s+(["\']?)([^"\']+)\1', q)
                if manu_match:
                    m = manu_match.group(2)
                    return f"SELECT * FROM supply_records WHERE Manufacturer LIKE '%{m}%'"
            if 'facility' in q:
                return "SELECT * FROM supply_records LIMIT 10"
        return None

    def _generate_generic_queries(self, q: str) -> Optional[str]:
        if 'vendor' in q:
            return ("SELECT Vendor, SUM(TotalSpend) AS TotalSpend, COUNT(*) AS TransactionCount "
                    "FROM supply_records WHERE Vendor IS NOT NULL "
                    "GROUP BY Vendor ORDER BY TotalSpend DESC")
        if 'manufacturer' in q:
            return ("SELECT Manufacturer, SUM(TotalSpend) AS TotalSpend, COUNT(*) AS TransactionCount "
                    "FROM supply_records WHERE Manufacturer IS NOT NULL "
                    "GROUP BY Manufacturer ORDER BY TotalSpend DESC")
        if any(word in q for word in ['item', 'product']):
            return ("SELECT ItemDesc, SUM(TotalSpend) AS TotalSpend, COUNT(*) AS TransactionCount "
                    "FROM supply_records WHERE ItemDesc IS NOT NULL "
                    "GROUP BY ItemDesc ORDER BY TotalSpend DESC")
        if 'facility' in q:
            return ("SELECT FacilityID, FacilityType, Region, SUM(TotalSpend) AS TotalSpend "
                    "FROM supply_records WHERE FacilityID IS NOT NULL "
                    "GROUP BY FacilityID, FacilityType, Region ORDER BY TotalSpend DESC")
        if 'region' in q:
            return ("SELECT Region, SUM(TotalSpend) AS TotalSpend, COUNT(*) AS TransactionCount "
                    "FROM supply_records WHERE Region IS NOT NULL "
                    "GROUP BY Region ORDER BY TotalSpend DESC")
        return None

    # --- Cleaning & safety --------------------------------------------------

    def _clean_and_validate_sql(self, query: str) -> str:
        logger.info(f"Cleaning raw SQL: '{query}'")
        if not query:
            raise ValueError("Empty SQL query")

        original_query = query
        query = re.sub(r'```sql\s*', '', query, flags=re.IGNORECASE)
        query = re.sub(r'\s*```', '', query)
        query = re.sub(r'`+', '', query)
        query = re.sub(r'^[:\-\s]*', '', query, flags=re.MULTILINE)
        query = query.strip().rstrip(';').strip()

        logger.info(f"After cleanup - Original: '{original_query}' -> Cleaned: '{query}'")

        if not query.upper().startswith('SELECT'):
            raise ValueError("Only SELECT statements are allowed")

        for pattern in self.dangerous_patterns:
            if pattern.search(query):
                raise ValueError("Unsafe SQL operation detected")

        return query

    # --- Deterministic top-N formatting ------------------------------------

    def _format_top_n_response(self, kind: str, results: List[Dict], n: int) -> str:
        """
        Deterministic bullets:
        - 1) <Name> — $X
        - 2) <Name> — $Y
        Only uses returned rows; no percentages/txn counts.
        """
        name_key = 'Vendor' if kind == 'Vendor' else 'Manufacturer'
        bullets = []
        for i, r in enumerate(results[:n], 1):
            name = r.get(name_key, 'Unknown')
            amt = float(r.get('TotalSpend') or 0.0)
            bullets.append(f"- {i}) {name} — ${amt:,.2f}")
        return "\n".join(bullets) if bullets else "- No results"

    # --- LLM natural response ----------------------------------------------

    def _create_natural_response(self, question: str, results: List[Dict]) -> str:
        if not results:
            return "- No data found matching your question"

        max_tokens = self._calculate_response_tokens(question, results)
        try:
            data_preview = self._create_enhanced_data_preview(results, question)
            prompt = f"""You are Earl, an AI assistant specializing in supply chain management and procurement data analysis.

RESPONSE FORMAT - CRITICAL:
- Use ONLY bullet points (-, *, or numbers)
- One key insight per line - be concise and direct
- No paragraphs, explanations, or connecting phrases
- Start each bullet with the core insight immediately
- Maximum 4-5 bullet points per response
- Format currency as $X,XXX.XX and percentages as X%

USER QUESTION: {question}

QUERY RESULTS:
{data_preview}

RESPONSE:"""
            response = self.llama_service.query(prompt, max_tokens=max_tokens, temperature=0.1)
            return (response or "").strip()
        except Exception as e:
            logger.warning(f"LLM response generation failed: {e}, using fallback")
            return self._create_enhanced_fallback_response(question, results)

    def _calculate_response_tokens(self, question: str, results: List[Dict]) -> int:
        base_tokens = 200
        if len(results) > 15:
            return 400
        if any(word in question.lower() for word in ['list', 'show', 'all', 'compare']):
            return 350
        if len(results) == 1 and len(str(results[0])) > 200:
            return 300
        return base_tokens

    # --- Data previews for LLM ---------------------------------------------

    def _create_enhanced_data_preview(self, results: List[Dict], question: str) -> str:
        if not results:
            return "No data found."
        q = question.lower()
        if len(results) == 1:
            return self._format_single_result(results[0], q)
        return self._format_multiple_results(results, q)

    def _format_single_result(self, result: Dict, question_lower: str) -> str:
        preview_parts = []
        priority_keys = self._get_priority_keys(question_lower)
        for key in priority_keys:
            if key in result and result[key] is not None:
                value = result[key]
                if 'Spend' in key or 'Price' in key:
                    preview_parts.append(f"{key}: ${float(value):,.2f}")
                else:
                    preview_parts.append(f"{key}: {value}")
        for key, value in result.items():
            if key not in priority_keys and value is not None:
                if 'Spend' in key or 'Price' in key:
                    preview_parts.append(f"{key}: ${float(value):,.2f}")
                else:
                    preview_parts.append(f"{key}: {value}")
        return " | ".join(preview_parts) if preview_parts else str(result)

    def _format_multiple_results(self, results: List[Dict], question_lower: str) -> str:
        if len(results) <= 25:
            return self._format_detailed_list(results)
        return self._format_summary_with_top_items(results)

    def _get_priority_keys(self, question_lower: str) -> List[str]:
        if 'vendor' in question_lower or 'supplier' in question_lower:
            return ['Vendor', 'TotalSpend', 'TransactionCount']
        if 'manufacturer' in question_lower or 'maker' in question_lower:
            return ['Manufacturer', 'TotalSpend', 'TransactionCount']
        if 'item' in question_lower or 'product' in question_lower:
            return ['ItemDesc', 'TotalSpend', 'TransactionCount']
        if 'facility' in question_lower or 'hospital' in question_lower:
            return ['FacilityID', 'FacilityType', 'Region', 'TotalSpend']
        if 'region' in question_lower:
            return ['Region', 'TotalSpend', 'TransactionCount']
        return ['TotalSpend', 'TransactionCount']

    def _format_detailed_list(self, results: List[Dict]) -> str:
        actual_values = []
        for i, r in enumerate(results, 1):
            parts = []
            name_key = self._get_primary_name_key(r)
            if name_key:
                parts.append(r[name_key] or f'Unknown {name_key}')
            if 'TotalSpend' in r and r['TotalSpend'] is not None:
                spend = float(r['TotalSpend'])
                parts.append(f"${spend:,.2f}")
            if 'TransactionCount' in r and r['TransactionCount'] is not None:
                count = int(r['TransactionCount'])
                parts.append(f"{count} transactions")
            for key in ['AverageSpend', 'Quantity', 'PricePaid']:
                if key in r and r[key] is not None:
                    value = float(r[key])
                    if 'Price' in key or 'Spend' in key:
                        parts.append(f"{key}: ${value:,.2f}")
                    else:
                        parts.append(f"{key}: {value:,.0f}")
            actual_values.append(f"{i}. {' | '.join(parts)}")
        return "ACTUAL DATABASE RESULTS:\n" + "\n".join(actual_values)

    def _format_summary_with_top_items(self, results: List[Dict]) -> str:
        summary_parts = [f"Found {len(results)} records"]
        total_spend = sum(float(r.get('TotalSpend', 0) or 0) for r in results)
        if total_spend > 0:
            summary_parts.append(f"Total spend: ${total_spend:,.2f}")
        total_transactions = sum(int(r.get('TransactionCount', 1) or 1) for r in results)
        summary_parts.append(f"Total transactions: {total_transactions:,}")

        top_entries = []
        for r in results[:10]:
            entry_parts = []
            name_key = self._get_primary_name_key(r)
            if name_key:
                entry_parts.append(str(r[name_key]))
            if 'TotalSpend' in r and r['TotalSpend']:
                entry_parts.append(f"${float(r['TotalSpend']):,.2f}")
            if entry_parts:
                top_entries.append(' - '.join(entry_parts))
        if top_entries:
            summary_parts.append("Top entries:\n" + "\n".join(f"{i+1}. {entry}" for i, entry in enumerate(top_entries)))
        return " | ".join(summary_parts[:2]) + "\n\n" + summary_parts[2] if len(summary_parts) > 2 else " | ".join(summary_parts)

    def _get_primary_name_key(self, record: Dict) -> Optional[str]:
        for key in ['Vendor', 'Manufacturer', 'ItemDesc', 'Region', 'FacilityID']:
            if key in record and record[key]:
                return key
        return None

    # --- Fallback response (no LLM) ----------------------------------------

    def _create_enhanced_fallback_response(self, question: str, results: List[Dict]) -> str:
        q = question.lower()
        if not results:
            return "- No matching records found in the supply chain database"
        if len(results) == 1:
            return self._format_single_result_fallback_bullets(results[0], q)
        return self._format_multiple_results_fallback_bullets(results, q)

    def _format_single_result_fallback_bullets(self, result: Dict, question_lower: str) -> str:
        bullets = []
        if 'TotalSpend' in result and len(result) <= 3:
            value = float(result['TotalSpend']) if result['TotalSpend'] else 0
            if any(word in question_lower for word in ['total', 'sum']):
                bullets.append(f"- Total spend: ${value:,.2f}")
            elif any(word in question_lower for word in ['average', 'avg']):
                bullets.append(f"- Average spend: ${value:,.2f}")
            else:
                bullets.append(f"- Spend amount: ${value:,.2f}")
        elif any(key in result for key in ['TransactionCount', 'VendorCount', 'ManufacturerCount', 'ItemCount', 'FacilityCount']):
            for key, value in result.items():
                if 'Count' in key and value is not None:
                    count_type = key.replace('Count', '').lower()
                    bullets.append(f"- {count_type.title()} count: {int(value):,}")
        else:
            for key, value in result.items():
                if value is not None:
                    if key == 'TotalSpend':
                        bullets.append(f"- Spend amount: ${float(value):,.2f}")
                    elif key in ['Vendor', 'Manufacturer', 'ItemDesc', 'Region', 'FacilityID', 'FacilityType']:
                        bullets.append(f"- {key}: {value}")
        return "\n".join(bullets) if bullets else "- Found one matching record"

    def _format_multiple_results_fallback_bullets(self, results: List[Dict], question_lower: str) -> str:
        bullets = []
        total_spend = sum(float(r.get('TotalSpend', 0) or 0) for r in results)
        data_type = "records"
        if any('vendor' in key.lower() for r in results for key in r.keys()):
            data_type = "vendors"
        elif any('manufacturer' in key.lower() for r in results for key in r.keys()):
            data_type = "manufacturers"
        elif any('itemdesc' in key.lower() for r in results for key in r.keys()):
            data_type = "items"
        elif any('region' in key.lower() for r in results for key in r.keys()):
            data_type = "regions"
        elif any('facility' in key.lower() for r in results for key in r.keys()):
            data_type = "facilities"

        bullets.append(f"- Found {len(results)} {data_type}")
        if total_spend > 0:
            bullets.append(f"- Total spend: ${total_spend:,.2f}")
            if len(results) > 1:
                avg_spend = total_spend / len(results)
                singular = data_type[:-1] if data_type.endswith('s') else data_type
                bullets.append(f"- Average spend per {singular}: ${avg_spend:,.2f}")

        if len(results) > 1:
            name_key = self._get_primary_name_key(results[0])
            if name_key and len(results) <= 5:
                top_items = []
                for r in results[:3]:
                    if name_key in r and r[name_key]:
                        spend = r.get('TotalSpend', 0)
                        if spend:
                            top_items.append(f"{r[name_key]} (${float(spend):,.2f})")
                        else:
                            top_items.append(str(r[name_key]))
                if top_items:
                    bullets.append(f"- Top entries: {', '.join(top_items)}")
        return "\n".join(bullets)

    # --- Recommendations & summary -----------------------------------------

    def _get_contextual_recommendations(self, question: str, results: List[Dict]) -> List[str]:
        recommendations: List[str] = []
        q = question.lower()
        if results:
            has_vendors = any('Vendor' in r for r in results)
            has_manufacturers = any('Manufacturer' in r for r in results)
            has_items = any('ItemDesc' in r for r in results)
            has_facilities = any('FacilityID' in r for r in results)
            has_regions = any('Region' in r for r in results)
            has_spend = any('TotalSpend' in r for r in results)
            has_time_data = any(r.get('Year') or r.get('Month') for r in results)

            if 'vendor' in q and has_vendors:
                recommendations.extend([
                    "Compare vendor performance across different time periods",
                    "Analyze vendor pricing trends and cost variations",
                    "Identify potential alternative suppliers for cost optimization",
                ])
            elif 'manufacturer' in q and has_manufacturers:
                recommendations.extend([
                    "Compare manufacturer performance across categories",
                    "Analyze manufacturer pricing trends and discounts",
                    "Assess dependency risk on top manufacturers",
                ])
            elif any(word in q for word in ['total', 'spend', 'cost']) and has_spend:
                recommendations.extend([
                    "Break down spending by vendor or product category",
                    "Analyze spending trends over time (monthly/yearly)",
                    "Compare spending across different regions or facilities",
                ])
            elif any(word in q for word in ['item', 'product']) and has_items:
                recommendations.extend([
                    "Compare prices for this item across different vendors",
                    "Analyze purchase volume trends for this product",
                    "Find similar products or alternatives",
                ])
            elif 'region' in q and has_regions:
                recommendations.extend([
                    "Compare regional spending patterns and efficiency",
                    "Analyze top vendors by region",
                    "Identify regional procurement opportunities",
                ])
            elif 'facility' in q and has_facilities:
                recommendations.extend([
                    "Compare facility spending and procurement patterns",
                    "Analyze facility-specific vendor relationships",
                    "Identify cost-saving opportunities across facilities",
                ])
            elif any(word in q for word in ['trend', 'time', 'monthly', 'yearly']) and has_time_data:
                recommendations.extend([
                    "Analyze seasonal purchasing patterns",
                    "Compare year-over-year spending growth",
                    "Identify procurement optimization opportunities",
                ])
            elif any(word in q for word in ['top', 'bottom', 'best', 'worst']):
                recommendations.extend([
                    "Analyze what makes top performers successful",
                    "Compare performance metrics across categories",
                    "Investigate factors behind performance differences",
                ])
            else:
                if has_vendors and has_spend:
                    recommendations.append("Analyze vendor spending patterns and relationships")
                if has_manufacturers and has_spend:
                    recommendations.append("Analyze manufacturer spending patterns")
                if has_time_data:
                    recommendations.append("Explore trends and patterns over time")
                if has_regions:
                    recommendations.append("Compare performance across different regions")
        else:
            recommendations = [
                "Try broader search terms or different time periods",
                "Check for data availability in your dataset",
                "Ask about general patterns or summaries instead",
            ]
        return recommendations[:3]

    def _summarize_data(self, results: List[Dict]) -> Dict[str, Any]:
        if not results:
            return {"total_records": 0}
        total_spend = sum(float(r.get('TotalSpend', 0) or 0) for r in results)
        unique_vendors = len(set(r.get('Vendor') for r in results if r.get('Vendor')))
        unique_manufacturers = len(set(r.get('Manufacturer') for r in results if r.get('Manufacturer')))
        unique_items = len(set(r.get('ItemDesc') for r in results if r.get('ItemDesc')))
        unique_regions = len(set(r.get('Region') for r in results if r.get('Region')))
        unique_facilities = len(set(r.get('FacilityID') for r in results if r.get('FacilityID')))

        return {
            "total_records": len(results),
            "total_spend": round(total_spend, 2),
            "average_spend": round(total_spend / len(results), 2) if len(results) > 0 else 0,
            "unique_vendors": unique_vendors,
            "unique_manufacturers": unique_manufacturers,
            "unique_items": unique_items,
            "unique_regions": unique_regions,
            "unique_facilities": unique_facilities,
        }

    # --- Utility ------------------------------------------------------------

    def _is_greeting(self, text: str) -> bool:
        t = text.lower().strip()
        greetings = {'hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening'}
        return any(t.startswith(g) for g in greetings) and len(t.split()) <= 3

    def _has_data(self) -> bool:
        logger.info("Checking if supply_records table has data...")
        try:
            result = self.sql_service.query_items("SELECT COUNT(*) as count FROM supply_records")
            logger.info(f"Data check result: {result}")
            has_data = result[0]['count'] > 0 if result else False
            logger.info(f"Has data = {has_data} (count: {result[0]['count'] if result else 'No result'})")
            return has_data
        except Exception as e:
            logger.error(f"Failed to check data availability: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def _greeting_response(self) -> Dict[str, Any]:
        return {
            "success": True,
            "insights": "- Supply chain analytics ready\n- Ask about vendors, spending, facilities, or trends",
            "data_summary": {"total_records": 0},
            "recommendations": [
                "Ask about vendor spending patterns or performance",
                "Explore product categories and cost analysis",
                "Analyze trends over time or compare across regions",
            ],
            "result_count": 0,
            "sql_query": None,
        }

    def _no_data_response(self) -> Dict[str, Any]:
        return {
            "success": False,
            "insights": "- No supply chain data available\n- Please upload your data successfully",
            "data_summary": {"total_records": 0},
            "recommendations": [
                "Check if your CSV file was uploaded correctly",
                "Verify the data format matches expectations",
                "Try uploading your data again",
            ],
            "result_count": 0,
            "sql_query": None,
        }

    def _error_response(self, error: str) -> Dict[str, Any]:
        return {
            "success": False,
            "insights": "- Having trouble processing your question\n- Try rephrasing or asking something more specific",
            "data_summary": {"total_records": 0},
            "recommendations": [
                "Try asking about specific vendors or products",
                "Use simpler, more direct questions",
                "Ask about spending or quantities",
            ],
            "result_count": 0,
            "error": error,
            "sql_query": None,
        }


# Singleton instance
text_to_sql_service = TextToSQLService()

def get_text_to_sql_service() -> TextToSQLService:
    """Get the singleton TextToSQLService instance."""
    return text_to_sql_service
