"""Currency conversion agent backed only by official ECB reference rates.

Rates come from the Frankfurter API, restricted to the European Central Bank
provider: https://api.frankfurter.dev/v2/providers/ecb/rate/{base}/{quote}
"""

from datetime import date as Date, datetime, timezone
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

import httpx
from google.adk import Agent

FRANKFURTER_ECB_URL = "https://api.frankfurter.dev/v2/providers/ecb/rate/{base}/{quote}"
SOURCE = "European Central Bank (ECB) euro foreign exchange reference rates, via the Frankfurter API"
HTTP_TIMEOUT_SECONDS = 10.0


def _today_utc() -> Date:
    return datetime.now(timezone.utc).date()


def _error(error_type: str, message: str) -> dict:
    return {"status": "error", "error_type": error_type, "message": message}


def get_today() -> dict:
    """Returns today's date in UTC.

    Use this before resolving any relative date such as "today", "yesterday",
    "last Friday" or "a month ago" into a YYYY-MM-DD date.

    Returns:
        dict: status, today's date (YYYY-MM-DD), the weekday name and the timezone.
    """
    today = _today_utc()
    return {
        "status": "success",
        "today": today.isoformat(),
        "weekday": today.strftime("%A"),
        "timezone": "UTC",
    }


def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str,
    date: str | None = None,
) -> dict:
    """Converts an amount between two currencies using the official ECB reference rate.

    The exchange rate is fetched from the European Central Bank data and the
    multiplication is done in code. Always use the returned values as-is.

    Args:
        amount: The amount of money to convert. Must be greater than zero.
        from_currency: ISO 4217 code of the source currency, for example "EUR".
        to_currency: ISO 4217 code of the target currency, for example "USD".
        date: Optional date of the rate in YYYY-MM-DD format. Omit it for the
            latest published rate. Must not be in the future.

    Returns:
        dict: On success: status, amount, from_currency, to_currency, rate,
        rate_date, requested_date, result, rate_date_differs, note, source and
        source_url. On failure: status "error", error_type and message.
    """
    # --- Validate input -------------------------------------------------------
    base = (from_currency or "").strip().upper()
    quote = (to_currency or "").strip().upper()
    for code in (base, quote):
        if len(code) != 3 or not code.isalpha():
            return _error(
                "invalid_currency",
                f"'{code}' is not a valid 3-letter ISO 4217 currency code.",
            )

    try:
        amount_dec = Decimal(str(amount))
    except InvalidOperation:
        return _error("invalid_amount", f"'{amount}' is not a valid number.")
    if not amount_dec.is_finite() or amount_dec <= 0:
        return _error("invalid_amount", "The amount must be a number greater than zero.")

    requested: Date | None = None
    if date:
        try:
            requested = Date.fromisoformat(date.strip())
        except ValueError:
            return _error("invalid_date", f"'{date}' is not a valid date in YYYY-MM-DD format.")
        if requested > _today_utc():
            return _error(
                "future_date",
                f"{requested.isoformat()} is in the future. ECB only publishes past and current rates.",
            )

    # --- Call the ECB provider endpoint ---------------------------------------
    url = FRANKFURTER_ECB_URL.format(base=base, quote=quote)
    params = {"date": requested.isoformat()} if requested else None
    try:
        response = httpx.get(
            url,
            params=params,
            timeout=HTTP_TIMEOUT_SECONDS,
            headers={"Accept": "application/json", "User-Agent": "currency-agent-adk"},
        )
    except httpx.HTTPError as exc:
        return _error("network_error", f"Could not reach the rates service: {exc.__class__.__name__}.")

    if response.status_code == 404:
        when = requested.isoformat() if requested else "the latest date"
        return _error(
            "no_rate",
            f"The ECB has no published {base}/{quote} rate for {when}. The date may be "
            "before ECB coverage for one of these currencies (ECB data starts on "
            "1999-01-04), or a currency may have been discontinued.",
        )
    if response.status_code == 422:
        try:
            detail = response.json().get("message", "")
        except ValueError:
            detail = ""
        return _error(
            "invalid_request",
            f"The request was rejected: {detail or 'invalid parameters'}. A currency may not be "
            "published by the ECB, or the date may be invalid.",
        )
    if response.status_code != 200:
        return _error("service_error", f"The rates service returned HTTP {response.status_code}.")

    try:
        data = response.json()
        rate = Decimal(str(data["rate"]))
        rate_date = Date.fromisoformat(data["date"])
    except (ValueError, KeyError, TypeError, InvalidOperation):
        return _error("service_error", "The rates service returned an unexpected response.")

    # --- Do the math in code ----------------------------------------------------
    result = (amount_dec * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

    # --- Explain when the rate date differs from the requested date ------------
    target = requested or _today_utc()
    rate_date_differs = rate_date != target
    if not rate_date_differs:
        note = "The ECB published a reference rate on the requested date."
    elif requested:
        note = (
            f"The ECB did not publish a reference rate on {target.isoformat()} "
            f"({target.strftime('%A')}), which is a weekend or a TARGET holiday. "
            f"The most recent earlier rate, from {rate_date.isoformat()} "
            f"({rate_date.strftime('%A')}), was used."
        )
    else:
        note = (
            f"No ECB rate has been published yet for today ({target.isoformat()}, "
            f"{target.strftime('%A')}). The ECB publishes once per business day around "
            f"16:00 CET and not on weekends or TARGET holidays, so the latest rate, from "
            f"{rate_date.isoformat()} ({rate_date.strftime('%A')}), was used."
        )

    return {
        "status": "success",
        "amount": float(amount_dec),
        "from_currency": base,
        "to_currency": quote,
        "rate": float(rate),
        "rate_date": rate_date.isoformat(),
        "requested_date": requested.isoformat() if requested else None,
        "result": float(result),
        "rate_date_differs": rate_date_differs,
        "note": note,
        "source": SOURCE,
        "source_url": str(response.url),
    }


INSTRUCTION = """
You are a currency conversion assistant. Your ONLY source of exchange rates is
the official European Central Bank (ECB) reference rate data returned by the
`convert_currency` tool.

Rules:
1. Language: always answer in the same language the user writes in.
2. Never invent, estimate, remember or guess exchange rates. If you do not have
   a rate from `convert_currency`, call the tool. If the tool returns an error,
   explain it to the user and do not provide a number.
3. Never do arithmetic yourself. Report the `rate` and `result` exactly as the
   tool returns them. For several amounts or currencies, call the tool once per
   conversion.
4. Dates: for any relative date ("today", "yesterday", "last Friday",
   "two weeks ago"), call `get_today` first, compute the YYYY-MM-DD date, then
   pass it as `date`. For "now" or "latest", omit `date`.
5. Publication gaps: the ECB publishes reference rates once per business day
   (around 16:00 CET), not on weekends or TARGET holidays (such as 1 January,
   Good Friday, Easter Monday, 1 May, 25 and 26 December). When the tool
   reports `rate_date_differs: true`, clearly tell the user that the ECB did
   not publish a rate for the requested day and which earlier date's rate was
   used, based on the tool's `note`.
6. In every answer with a conversion, state: the amount and result, the rate,
   the rate date, and the source (ECB reference rates).
7. End every answer that contains a rate or conversion with a short disclaimer,
   translated into the user's language, equivalent to: "Reference only: ECB
   reference rates are published for information purposes and are not the
   rates offered by banks or for transactions."
8. Only handle currency conversion and exchange-rate questions. Politely
   decline unrelated requests.
"""

root_agent = Agent(
    name="currency_agent",
    model="gemini-3.5-flash",
    description="Converts currencies using official European Central Bank reference rates.",
    instruction=INSTRUCTION,
    tools=[get_today, convert_currency],
)
