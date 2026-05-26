# Channex Security Policy

**Archived for:** Fine Star d.o.o. / stay.hr (May 2026)

## Standards referenced

- ISO 27001 (technical specifications alignment stated)
- PCI DSS (technical specifications alignment stated)
- EU Data Directive / GDPR (Model Clauses with customers/partners)

## Data stored by Channex

**Authentication:** usernames, email addresses

**Channel management:**

- Property details (name, address, email, facilities, images, room types, rate plans, availability, prices, restrictions)
- Booking metadata (customer name, guest names, address, **card details if present**)

## Data retention (operational)

| Data type | Retention |
|-----------|-----------|
| Properties (no channels) | Removed after **3 months** |
| Bookings | Deleted **3 months after departure** |
| ARI (past dates) | Removed **daily** |
| Credit card info (if stored) | Until **7 days after departure** |
| Account data after cancellation | Within **30 days** (or on request) |

## Security measures (summary)

- Change control, employee training, restricted production access
- Data centres: ISO 27001, PCI DSS, physical access controls
- Firewalls (deny-all default), VLAN segregation, no customer root access
- Security patches applied per vendor policy

## Conclusion

Defense-in-depth across physical, infrastructure, application, and policy layers.

---

*Summary of Channex Security Policy bundled with Customer Agreement. Relevant for stay.hr: minimize card data sent to Channex; booking PII flows through processor chain.*
