# CafeCorner interview notes

1. **What does the application do?**  
   Customers browse and order from a cafe menu; staff manage orders and counter coupons; admins manage the menu and see sales; a separate printer client receives receipt jobs.

2. **How do roles work?**  
   A `Profile` has one of CUSTOMER, STAFF, ADMIN, or PRINTER and synchronizes the user's group. DRF permission classes check those groups, while order querysets scope customer reads to their own records.

3. **How is double coupon redemption prevented?**  
   In a transaction, one conditional database update matches the code only if it is unused and unexpired. Success requires exactly one affected row; the next request gets a conflict/error.

4. **What does the coupon concurrency test prove?**  
   It has two attempts start from the same stale unused state, then verifies only the first conditional update can change the row. It proves the conditional-update guard's result, not real threaded contention, production scheduling, or PostgreSQL performance.

5. **What if two staff advance one order at once?**  
   The order update includes both its ID and expected current status. Only one update can match; the loser gets HTTP 409. Status history is written in the same transaction as the winner's change.

6. **Why snapshot `unit_price` on `OrderItem`?**  
   Menu prices can change after checkout. The snapshot keeps the customer's historical total and the order's printed receipt stable.

7. **Why is there a `PRINTING` status and a claim timeout?**  
   Claiming conditionally changes PENDING to PRINTING so two clients cannot claim a job simultaneously. A timestamped lease returns abandoned work to PENDING after a timeout if a Raspberry Pi or network fails.

8. **Why restrict the printer token?**  
   A printer only needs pending job details and claim/complete actions. A dedicated printer group and permission class deny it menus, orders, coupons, profile data, and staff requeue operations.

9. **How are printer failures retried?**  
   Failure increments a server-side retry counter. The job returns to PENDING until the configured limit, then stays FAILED for staff to inspect and manually requeue.

10. **What is an N+1 query problem, and how was it tested?**  
    It is when a list query is followed by one extra database query per row, such as fetching each order's items separately. Order/item relations use `select_related` and `prefetch_related`; tests compare query counts for 3 and 15 orders on the general list, `/mine/`, and `/queue/` endpoints and expect equal counts.

11. **Why can an anonymous API request return 403 instead of 401?**  
    DRF tries SessionAuthentication first. It does not send a `WWW-Authenticate` challenge for an unauthenticated request, so DRF reports permission denial as 403. Authenticated users without the required role also receive 403.

12. **How does polling detect changes to an old order?**  
    The optional `since` parameter filters `updated_at`; each transition sets it explicitly because conditional queryset updates bypass `auto_now`. This returns an old order when its status changes.

13. **How is collected-today revenue defined?**  
    The app sums totals only for COLLECTED orders whose `collected_at` falls on the current `Asia/Kolkata` local date. Top items use database aggregation and exclude cancelled orders.

14. **Why use polling instead of WebSockets?**  
    A few-second poll is simpler to run for one cafe and fits the lightweight dashboard. At larger concurrency, a broker-backed WebSocket or server-sent-event service could reduce repeated idle requests.

15. **What would you change to scale or productionize it?**  
    Move to PostgreSQL, add deployment-specific rate limits and broader audit logs, isolate queues by cafe location, add monitoring/backups and load tests, then evaluate a durable printer queue and push updates. Payments and inventory would need explicit workflows and reconciliation.
