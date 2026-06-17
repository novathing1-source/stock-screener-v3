
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Protocol
import math
import re
import traceback

try:
    import yfinance as yf
except Exception:
    yf = None

DISCLAIMER = (
    "This is only a stock screening tool and not financial advice. "
    "Passing the screen does not automatically mean a stock is a good investment. "
    "Always do your own research and consider speaking with a licensed financial professional."
)

DATA_SOURCE_NOTE = (
    "Default provider: yfinance / Yahoo Finance style data. Some fields can be missing, delayed, or inconsistent by company or region."
)

class DataProvider(Protocol):
    def resolve_company(self, company_name: str) -> Dict[str, Any]: ...
    def get_company_profile(self, ticker: str) -> Dict[str, Any]: ...
    def get_annual_financials(self, ticker: str) -> Dict[str, Any]: ...
    def get_quarterly_balance_sheet(self, ticker: str) -> Dict[str, Dict[str, Optional[float]]]: ...
    def get_quote_metrics(self, ticker: str) -> Dict[str, Any]: ...
    def get_eps_growth_estimate_percent(self, ticker: str) -> Optional[float]: ...

@dataclass
class ScreeningResult:
    company_name: str
    ticker: Optional[str]
    revenue_growth_by_year: List[Dict[str, Any]]
    passed_revenue_growth: Optional[bool]
    pe_ratio: Optional[float]
    passed_pe: Optional[bool]
    peg_ratio: Optional[float]
    passed_peg: Optional[bool]
    roe_by_year: List[Dict[str, Any]]
    average_roe: Optional[float]
    passed_roe: Optional[bool]
    quick_ratio: Optional[float]
    passed_quick_ratio: Optional[bool]
    final_decision: str
    explanation: str
    missing_data_warnings: List[str]
    disclaimer: str = DISCLAIMER
    screen_step_failed: Optional[str] = None
    provider_name: str = "yfinance"
    data_source_note: str = DATA_SOURCE_NOTE
    checks_detail: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company_name": self.company_name,
            "ticker": self.ticker,
            "revenue_growth_by_year": self.revenue_growth_by_year,
            "passed_revenue_growth": self.passed_revenue_growth,
            "pe_ratio": self.pe_ratio,
            "passed_pe": self.passed_pe,
            "peg_ratio": self.peg_ratio,
            "passed_peg": self.passed_peg,
            "roe_by_year": self.roe_by_year,
            "average_roe": self.average_roe,
            "passed_roe": self.passed_roe,
            "quick_ratio": self.quick_ratio,
            "passed_quick_ratio": self.passed_quick_ratio,
            "final_decision": self.final_decision,
            "explanation": self.explanation,
            "missing_data_warnings": self.missing_data_warnings,
            "disclaimer": self.disclaimer,
            "screen_step_failed": self.screen_step_failed,
            "provider_name": self.provider_name,
            "data_source_note": self.data_source_note,
            "checks_detail": self.checks_detail or [],
        }

def normalize_name(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"(inc|inc\.|corp|corp\.|corporation|company|co\.|ltd|ltd\.|plc|holdings?)", "", name)
    name = re.sub(r"[^a-z0-9 ]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name

def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except Exception:
        return None

def pct(decimal_value: Optional[float]) -> Optional[float]:
    return None if decimal_value is None else decimal_value * 100.0

class YFinanceProvider:
    def __init__(self) -> None:
        if yf is None:
            raise ImportError("yfinance is not installed. Install with: pip install yfinance pandas")

    def resolve_company(self, company_name: str) -> Dict[str, Any]:
        normalized = normalize_name(company_name)
        quotes = []
        try:
            search = yf.Search(query=company_name, max_results=10)
            quotes = getattr(search, "quotes", []) or []
        except Exception:
            quotes = []
        if not quotes:
            guess = company_name.strip().upper()
            try:
                info = yf.Ticker(guess).info or {}
                if info.get("symbol"):
                    return {
                        "ticker": info.get("symbol"),
                        "resolved_name": info.get("longName") or info.get("shortName") or company_name,
                        "quote_type": info.get("quoteType"),
                        "exchange": info.get("exchange"),
                    }
            except Exception:
                pass
            raise ValueError(f"Could not identify a public ticker for '{company_name}'. It may be private, misspelled, or unavailable.")

        def score_quote(q: Dict[str, Any]) -> Tuple[int, int]:
            qname = normalize_name(q.get("shortname") or q.get("longname") or "")
            qtype = str(q.get("quoteType", "")).lower()
            type_score = 1 if qtype == "equity" else 0
            if qname == normalized:
                name_score = 3
            elif normalized in qname or qname in normalized:
                name_score = 2
            elif any(part in qname for part in normalized.split()):
                name_score = 1
            else:
                name_score = 0
            return (type_score, name_score)

        quotes = sorted(quotes, key=score_quote, reverse=True)
        for quote in quotes:
            qtype = str(quote.get("quoteType", "")).lower()
            if qtype in {"equity", "etf", "mutualfund"} and quote.get("symbol"):
                return {
                    "ticker": quote.get("symbol"),
                    "resolved_name": quote.get("shortname") or quote.get("longname") or company_name,
                    "quote_type": quote.get("quoteType"),
                    "exchange": quote.get("exchange"),
                }
        raise ValueError(f"Found matches for '{company_name}', but none looked like a usable public stock ticker.")

    def get_company_profile(self, ticker: str) -> Dict[str, Any]:
        info = yf.Ticker(ticker).info or {}
        return {
            "symbol": info.get("symbol") or ticker,
            "longName": info.get("longName") or info.get("shortName") or ticker,
            "quoteType": info.get("quoteType"),
            "exchange": info.get("exchange"),
            "currentPrice": info.get("currentPrice") or info.get("regularMarketPrice"),
            "trailingPE": info.get("trailingPE"),
            "pegRatio": info.get("pegRatio"),
            "dilutedEpsTTM": info.get("trailingEps") or info.get("epsTrailingTwelveMonths"),
            "quickRatio": info.get("quickRatio"),
        }

    def _normalize_frame(self, df) -> Dict[str, Dict[str, Optional[float]]]:
        out = {}
        if df is None or getattr(df, "empty", True):
            return out
        try:
            cols = [str(c.date()) if hasattr(c, "date") else str(c) for c in df.columns]
        except Exception:
            cols = [str(c) for c in df.columns]
        for row_name in df.index:
            row_vals = {}
            for col, value in zip(cols, df.loc[row_name].tolist()):
                row_vals[col] = safe_float(value)
            out[str(row_name)] = row_vals
        return out

    def get_annual_financials(self, ticker: str) -> Dict[str, Any]:
        t = yf.Ticker(ticker)
        income, bs = None, None
        for attr in ["income_stmt", "financials"]:
            try:
                income = getattr(t, attr)
                if income is not None and not income.empty:
                    break
            except Exception:
                pass
        for attr in ["balance_sheet", "balancesheet"]:
            try:
                bs = getattr(t, attr)
                if bs is not None and not bs.empty:
                    break
            except Exception:
                pass
        return {"income_statement": self._normalize_frame(income), "balance_sheet": self._normalize_frame(bs)}

    def get_quarterly_balance_sheet(self, ticker: str) -> Dict[str, Dict[str, Optional[float]]]:
        t = yf.Ticker(ticker)
        qbs = None
        for attr in ["quarterly_balance_sheet", "quarterly_balancesheet"]:
            try:
                qbs = getattr(t, attr)
                if qbs is not None and not qbs.empty:
                    break
            except Exception:
                pass
        return self._normalize_frame(qbs)

    def get_quote_metrics(self, ticker: str) -> Dict[str, Any]:
        p = self.get_company_profile(ticker)
        return {
            "current_price": safe_float(p.get("currentPrice")),
            "trailing_pe": safe_float(p.get("trailingPE")),
            "peg_ratio": safe_float(p.get("pegRatio")),
            "diluted_eps_ttm": safe_float(p.get("dilutedEpsTTM")),
            "quick_ratio": safe_float(p.get("quickRatio")),
        }

    def get_eps_growth_estimate_percent(self, ticker: str) -> Optional[float]:
        try:
            info = yf.Ticker(ticker).info or {}
            eg = safe_float(info.get("earningsGrowth"))
            if eg is not None:
                return pct(eg)
        except Exception:
            pass
        return None

def _first_available(statement: Dict[str, Dict[str, Optional[float]]], keys: List[str]):
    for key in keys:
        if key in statement:
            return statement[key]
    return None

def _sort_series(series: Dict[str, Optional[float]]):
    items = list(series.items())
    items.sort(key=lambda kv: kv[0])
    return items

def _compute_revenue_growth(revenue_line: Dict[str, Optional[float]]):
    items = [(k, v) for k, v in _sort_series(revenue_line) if v is not None]
    output = []
    for i in range(1, len(items)):
        year, cur = items[i]
        prev_year, prev = items[i - 1]
        growth = ((cur - prev) / abs(prev) * 100.0) if prev not in (None, 0) and cur is not None else None
        output.append({
            "fiscal_year": year,
            "revenue": cur,
            "previous_fiscal_year": prev_year,
            "previous_revenue": prev,
            "growth_percent": round(growth, 2) if growth is not None else None,
        })
    return output

def _compute_roe(net_income: Dict[str, Optional[float]], equity: Dict[str, Optional[float]]):
    years = sorted(set(net_income.keys()) & set(equity.keys()))
    rows = []
    for y in years:
        ni = net_income.get(y)
        eq = equity.get(y)
        roe = None
        note = None
        if ni is None or eq is None:
            note = "Missing net income or shareholder equity."
        elif eq <= 0:
            note = "ROE not meaningful because shareholder equity is zero or negative."
        else:
            roe = (ni / eq) * 100.0
        rows.append({"fiscal_year": y, "net_income": ni, "shareholders_equity": eq, "roe_percent": round(roe, 2) if roe is not None else None, "note": note})
    return rows[-5:]

def _latest_key(series):
    return sorted(series.keys())[-1] if series else None

def _compute_quick_ratio(qbs):
    warnings = []
    cash = _first_available(qbs, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", "Cash"])
    sec = _first_available(qbs, ["Available For Sale Securities", "Other Short Term Investments", "Marketable Securities"])
    ar = _first_available(qbs, ["Accounts Receivable", "Receivables", "Net Receivables"])
    cur_liab = _first_available(qbs, ["Current Liabilities", "Total Current Liabilities"])
    if not cur_liab:
        return None, ["Missing current liabilities in the quarterly balance sheet."]
    latest = _latest_key(cur_liab)
    if latest is None:
        return None, ["Quarterly balance sheet had no usable date column."]
    c = cash.get(latest) if cash else None
    s = sec.get(latest) if sec else 0.0
    r = ar.get(latest) if ar else None
    cl = cur_liab.get(latest)
    if cl in (None, 0):
        return None, ["Current liabilities were missing or zero; quick ratio cannot be calculated."]
    if c is None:
        warnings.append("Cash value missing in the most recent quarter.")
    if r is None:
        warnings.append("Accounts receivable missing in the most recent quarter.")
    if c is None or r is None:
        return None, warnings + ["Not enough quarterly balance-sheet data to calculate quick ratio."]
    return round(((c or 0.0) + (s or 0.0) + (r or 0.0)) / cl, 2), warnings

def _build_checks(result):
    return [
        {"step": 1, "label": "Revenue growth ≥ 10% every year", "passed": result.passed_revenue_growth},
        {"step": 2, "label": "P/E ratio < 25", "passed": result.passed_pe},
        {"step": 3, "label": "PEG ratio < 2", "passed": result.passed_peg},
        {"step": 4, "label": "Average ROE > 5%", "passed": result.passed_roe},
        {"step": 5, "label": "Quick ratio > 1.5", "passed": result.passed_quick_ratio},
    ]

def _summary(result):
    pieces = [f"Company: {result.company_name}", f"Ticker: {result.ticker or 'Unavailable'}", f"Decision: {result.final_decision}", f"Why: {result.explanation}"]
    if result.missing_data_warnings:
        pieces.append("Warnings:")
        pieces.extend([f"- {w}" for w in result.missing_data_warnings])
    pieces.append(f"Data source note: {result.data_source_note}")
    pieces.append(f"Disclaimer: {result.disclaimer}")
    return "
".join(pieces)

def format_result_markdown(result_dict: Dict[str, Any]) -> str:
    r = result_dict["result"]
    lines = [f"# {r['company_name']} ({r['ticker'] or 'No ticker'})", f"**Decision:** {r['final_decision']}", f"**Explanation:** {r['explanation']}", "", "## Key numbers", f"- P/E ratio: {r['pe_ratio']}", f"- PEG ratio: {r['peg_ratio']}", f"- Average ROE: {r['average_roe']}", f"- Quick ratio: {r['quick_ratio']}", "", f"**Data source note:** {r['data_source_note']}", f"**Disclaimer:** {r['disclaimer']}"]
    if r["missing_data_warnings"]:
        lines.append("
## Warnings")
        lines.extend([f"- {w}" for w in r["missing_data_warnings"]])
    return "
".join(lines)

def analyze_stock(company_name: str, provider: Optional[DataProvider] = None) -> Dict[str, Any]:
    if not isinstance(company_name, str) or not company_name.strip():
        raise ValueError("company_name must be a non-empty string")
    provider = provider or YFinanceProvider()
    warnings = []
    result = ScreeningResult(company_name=company_name.strip(), ticker=None, revenue_growth_by_year=[], passed_revenue_growth=None, pe_ratio=None, passed_pe=None, peg_ratio=None, passed_peg=None, roe_by_year=[], average_roe=None, passed_roe=None, quick_ratio=None, passed_quick_ratio=None, final_decision="Could not analyze.", explanation="Analysis could not be completed.", missing_data_warnings=warnings)
    try:
        resolved = provider.resolve_company(company_name.strip())
        ticker = resolved.get("ticker")
        result.ticker = ticker
        result.company_name = resolved.get("resolved_name") or company_name.strip()
        profile = provider.get_company_profile(ticker)
        qtype = str(profile.get("quoteType") or resolved.get("quote_type") or "").lower()
        if qtype and qtype not in {"equity", "etf", "mutualfund"}:
            result.final_decision = "Stock data unavailable."
            result.explanation = f"'{company_name}' resolved to {ticker}, but it was not a standard public stock listing."
            result.screen_step_failed = "ticker_lookup"
            result.checks_detail = _build_checks(result)
            return {"result": result.to_dict(), "summary": _summary(result)}
        annual = provider.get_annual_financials(ticker)
        income = annual.get("income_statement", {})
        annual_bs = annual.get("balance_sheet", {})
        quote = provider.get_quote_metrics(ticker)
        revenue_line = _first_available(income, ["Total Revenue", "Revenue", "Operating Revenue"])
        if not revenue_line:
            result.final_decision = "Could not analyze revenue growth."
            result.explanation = "Missing annual revenue data."
            result.screen_step_failed = "revenue_growth"
            warnings.append("Revenue line was not available from the data provider.")
            result.checks_detail = _build_checks(result)
            return {"result": result.to_dict(), "summary": _summary(result)}
        revenues = {k: v for k, v in revenue_line.items() if v is not None}
        if len(revenues) < 5:
            result.final_decision = "Could not analyze revenue growth."
            result.explanation = "At least 5 fiscal years of annual revenue are required, but fewer were available."
            result.screen_step_failed = "revenue_growth"
            warnings.append("Insufficient annual revenue history.")
            result.checks_detail = _build_checks(result)
            return {"result": result.to_dict(), "summary": _summary(result)}
        last5 = dict(_sort_series(revenues)[-5:])
        growth_rows = _compute_revenue_growth(last5)
        result.revenue_growth_by_year = growth_rows
        if not growth_rows or any(r.get("growth_percent") is None for r in growth_rows):
            result.final_decision = "Could not analyze revenue growth."
            result.explanation = "Revenue growth could not be calculated for each required year."
            result.passed_revenue_growth = False
            result.screen_step_failed = "revenue_growth"
            warnings.append("One or more revenue years contained invalid data.")
            result.checks_detail = _build_checks(result)
            return {"result": result.to_dict(), "summary": _summary(result)}
        result.passed_revenue_growth = all(r["growth_percent"] >= 10.0 for r in growth_rows)
        if not result.passed_revenue_growth:
            result.final_decision = "STOP: Low revenue growth."
            result.explanation = "The company did not grow revenue by at least 10% in every year of the most recent 5-year annual window."
            result.screen_step_failed = "revenue_growth"
            result.checks_detail = _build_checks(result)
            return {"result": result.to_dict(), "summary": _summary(result)}
        pe = quote.get("trailing_pe")
        price = quote.get("current_price")
        eps = quote.get("diluted_eps_ttm")
        if pe is None:
            if eps is None or price is None:
                result.final_decision = "Could not analyze valuation."
                result.explanation = "Trailing P/E was unavailable, and there was not enough price/EPS data to calculate it."
                result.screen_step_failed = "pe_ratio"
                warnings.append("Missing trailing PE, current price, or diluted EPS TTM.")
                result.checks_detail = _build_checks(result)
                return {"result": result.to_dict(), "summary": _summary(result)}
            if eps <= 0:
                result.final_decision = "P/E not meaningful."
                result.explanation = "The company has zero or negative trailing earnings, so the P/E ratio is not meaningful."
                result.screen_step_failed = "pe_ratio"
                warnings.append("Negative or zero earnings make P/E unusable.")
                result.checks_detail = _build_checks(result)
                return {"result": result.to_dict(), "summary": _summary(result)}
            pe = price / eps
        result.pe_ratio = round(pe, 2)
        result.passed_pe = pe < 25.0
        if not result.passed_pe:
            result.final_decision = "Likely overvalued."
            result.explanation = "The current trailing P/E ratio is 25 or higher."
            result.screen_step_failed = "pe_ratio"
            result.checks_detail = _build_checks(result)
            return {"result": result.to_dict(), "summary": _summary(result)}
        peg = quote.get("peg_ratio")
        if peg is None:
            eps_growth = provider.get_eps_growth_estimate_percent(ticker)
            if eps_growth is None:
                result.final_decision = "Could not analyze PEG ratio."
                result.explanation = "PEG ratio was unavailable, and expected EPS growth estimates were not available to calculate it."
                result.screen_step_failed = "peg_ratio"
                warnings.append("Missing PEG ratio and expected EPS growth estimate.")
                result.checks_detail = _build_checks(result)
                return {"result": result.to_dict(), "summary": _summary(result)}
            if eps_growth <= 0:
                result.final_decision = "Could not analyze PEG ratio."
                result.explanation = "Expected EPS growth rate was zero or negative, so PEG is not meaningful for this screen."
                result.screen_step_failed = "peg_ratio"
                warnings.append("Expected EPS growth was non-positive.")
                result.checks_detail = _build_checks(result)
                return {"result": result.to_dict(), "summary": _summary(result)}
            peg = pe / eps_growth
        result.peg_ratio = round(peg, 2)
        result.passed_peg = peg < 2.0
        if not result.passed_peg:
            result.final_decision = "Low profit growth."
            result.explanation = "The PEG ratio is 2 or higher."
            result.screen_step_failed = "peg_ratio"
            result.checks_detail = _build_checks(result)
            return {"result": result.to_dict(), "summary": _summary(result)}
        net_income = _first_available(income, ["Net Income", "Net Income Common Stockholders", "Net Income Including Noncontrolling Interests"])
        equity = _first_available(annual_bs, ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest", "Total Stockholder Equity"])
        if not net_income or not equity:
            result.final_decision = "Could not analyze profitability."
            result.explanation = "Missing annual net income or shareholder equity data needed for ROE."
            result.screen_step_failed = "roe"
            warnings.append("Missing annual net income and/or shareholder equity lines.")
            result.checks_detail = _build_checks(result)
            return {"result": result.to_dict(), "summary": _summary(result)}
        roe_rows = _compute_roe(net_income, equity)
        result.roe_by_year = roe_rows
        valid_roe = [r["roe_percent"] for r in roe_rows if r.get("roe_percent") is not None]
        if len(roe_rows) < 5:
            result.final_decision = "Could not analyze profitability."
            result.explanation = "At least 5 years of overlapping net income and equity data are required for ROE analysis."
            result.screen_step_failed = "roe"
            warnings.append("Insufficient ROE history.")
            result.checks_detail = _build_checks(result)
            return {"result": result.to_dict(), "summary": _summary(result)}
        if len(valid_roe) < 5:
            result.final_decision = "ROE not meaningful."
            result.explanation = "ROE could not be meaningfully calculated for all of the last 5 fiscal years, usually because equity was zero or negative in one or more years."
            result.screen_step_failed = "roe"
            bad_years = [r['fiscal_year'] for r in roe_rows if r.get('roe_percent') is None]
            warnings.append(f"ROE not meaningful for years: {', '.join(bad_years)}")
            result.checks_detail = _build_checks(result)
            return {"result": result.to_dict(), "summary": _summary(result)}
        avg_roe = sum(valid_roe[-5:]) / 5.0
        result.average_roe = round(avg_roe, 2)
        result.passed_roe = avg_roe > 5.0
        if not result.passed_roe:
            result.final_decision = "Weak profitability."
            result.explanation = "The 5-year average ROE is 5% or lower."
            result.screen_step_failed = "roe"
            result.checks_detail = _build_checks(result)
            return {"result": result.to_dict(), "summary": _summary(result)}
        qbs = provider.get_quarterly_balance_sheet(ticker)
        qr, qr_warnings = _compute_quick_ratio(qbs)
        warnings.extend(qr_warnings)
        if qr is None:
            provider_qr = quote.get("quick_ratio")
            if provider_qr is None:
                result.final_decision = "Could not analyze liquidity."
                result.explanation = "The most recent quarterly balance sheet did not have enough data to calculate the quick ratio, and no fallback quick ratio was available."
                result.screen_step_failed = "quick_ratio"
                result.checks_detail = _build_checks(result)
                return {"result": result.to_dict(), "summary": _summary(result)}
            qr = provider_qr
            warnings.append("Used provider-supplied quick ratio fallback instead of direct balance-sheet calculation.")
        result.quick_ratio = round(qr, 2)
        result.passed_quick_ratio = qr > 1.5
        if not result.passed_quick_ratio:
            result.final_decision = "Liquidity issues."
            result.explanation = "The quick ratio is 1.5 or lower."
            result.screen_step_failed = "quick_ratio"
            result.checks_detail = _build_checks(result)
            return {"result": result.to_dict(), "summary": _summary(result)}
        result.final_decision = "Passes screen: Invest candidate."
        result.explanation = "The company passed all five screening checks: revenue growth, P/E, PEG, ROE, and quick ratio. That does NOT automatically mean the stock is a good investment—this is only a first-pass filter."
        result.checks_detail = _build_checks(result)
        return {"result": result.to_dict(), "summary": _summary(result)}
    except ValueError as e:
        result.final_decision = "Stock data unavailable."
        result.explanation = str(e)
        result.screen_step_failed = "ticker_lookup"
        result.checks_detail = _build_checks(result)
        return {"result": result.to_dict(), "summary": _summary(result)}
    except Exception as e:
        result.final_decision = "API/data error."
        result.explanation = f"An unexpected error occurred while analyzing the stock: {e}"
        result.screen_step_failed = "api_error"
        warnings.append(traceback.format_exc(limit=1))
        result.checks_detail = _build_checks(result)
        return {"result": result.to_dict(), "summary": _summary(result)}
