# CafeCorner design notes

## Coupon handling

Staff redeem coupons at the counter on a customer's behalf. Customers can list and view only coupons attached to their own orders. A successful redemption records the staff user and redemption time. The redemption endpoint is rate limited to reduce code guessing.

Coupon codes use 24 cryptographically random characters from an uppercase alphabet that omits ambiguous `0`, `O`, `1`, and `I` characters. Coupons expire 30 days after issuance by default; `COUPON_VALIDITY_DAYS` changes that period.

The order transition to `COLLECTED`, its status-history row, coupon issuance, and `COUPON_SLIP` print job share one database transaction. The transition uses a conditional update against the expected order status. Coupon redemption similarly updates only a matching, unused, unexpired code inside a transaction and checks the affected-row count.

The concurrent-redemption test simulates two callers that both observed the coupon as unused, then submits both conditional redemptions. The second attempt cannot update the row. This project uses SQLite for development; its coarse writer locks make threaded race tests unreliable, while the conditional-update behavior is the same database operation used on PostgreSQL.

## Dashboard dates

`Order.collected_at` is set during the `COLLECTED` transition and is used to decide which local day receives the revenue and top-item totals. `updated_at` continues to record any status transition, but later edits cannot move revenue between days. Dates use `TIME_ZONE = "Asia/Kolkata"` with `USE_TZ = True`. Dashboard summaries use database `COUNT` and `SUM` aggregation and include only `COLLECTED` orders in revenue and item sales.
