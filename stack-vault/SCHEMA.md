# Stack Vault — Field Dictionary (v1.0)

Canonical structure for every export. One JSON file per business:

```json
{
  "vault_version": "1.0",
  "exported_at": "2026-07-18T00:00:00Z",
  "business_profile": { ... },
  "tools": [ { ...one record per tool/affiliate program... } ]
}
```

Empty string = not filled in yet. The AI-Markdown export renders empty fields as `MISSING` on purpose — gaps are data.

**Never store secrets.** `credential_ref` and `api.key_ref` hold the *name of the entry in your password manager*, never the password or key itself.

---

## business_profile

### owner — Business Owner Contact Card
| Field | Meaning |
|---|---|
| `name` | Owner's full name |
| `email` | Best email for the owner |
| `photo_url` | Link to a current photo/headshot |
| `website` | Personal or main site |
| `social_links` | Social profiles, one per line |
| `contact_hours` | Hours you're reachable (with timezone) |
| `preferred_contact` | Best way to reach you (text/email/DM/call) |
| `vcard_url` | Contact-card link that works on iPhone/Android |

### brand
| Field | Meaning |
|---|---|
| `name` | Brand name (e.g. CASH.BOT) |
| `logo_url` | Link to logo files |
| `legal_entity` | LLC / corp name exactly as registered |
| `niche` | One line: what the brand does, for whom |
| `local_service_area` | Geographic area served, if any |
| `online_products` | Products/offers sold online, one per line |
| `affiliate_programs_promoted` | Programs you promote (summary — details live in `tools`) |
| `sponsorships` | Active sponsorship deals |
| `domain_provider` | Where your domains live |
| `next_domain_renewal` | Date the main domain renews |
| `trademarks` | Registered marks |
| `press` | Press mentions/links |
| `achievements_url` | Link to proof/achievements folder |
| `cloud_storage_url` | Link to the brand's master drive folder |

### audience
| Field | Meaning |
|---|---|
| `email_list_size` | Subscribers on your email list |
| `sms_list_size` | Numbers on your SMS list |
| `groups_combined_size` | Total members across all groups |
| `facebook_group_url` / `whop_group_url` / `instagram_community_url` / `other_communities` | Community links |
| `customer_data_enriched` | Is customer data enriched? (yes/no + tool) |
| `customer_data_tagged` | Is customer data grouped/tagged? (yes/no + how) |

### content_assets
| Field | Meaning |
|---|---|
| `brand_images` / `brand_videos` / `brand_written` | Links to asset folders |
| `prewritten_emails` | Link to email swipe folder |
| `automated_followup` | Follow-up automation in place? (what tool, what flows) |
| `daily_content` | What ships daily, where |
| `reviews` | Where reviews live + rough count |

### traffic_money
| Field | Meaning |
|---|---|
| `organic_traffic` / `social_traffic` / `paid_traffic` | Monthly visits per channel |
| `avg_leadflow` | New leads per month |
| `avg_cashflow` | Gross revenue per month (USD) |
| `avg_net_profit` | Net profit per month (USD) |
| `platform_ad_spend` | Monthly ad spend (USD) |
| `ad_platforms` | Where ads run |
| `hiring_marketing_spend` | Monthly spend on marketing help (USD) |
| `employee_spend` | Monthly payroll/contractor spend (USD) |
| `marketing_budget` | Estimated overall marketing budget (USD/mo) |
| `profit_share_pct` | Estimated % of profits shared |
| `trajectory` | up / flat / down + one line why |

### stack
| Field | Meaning |
|---|---|
| `websites` | Your sites, one per line |
| `social_profiles` | Brand profiles, one per line |
| `paid_apps` | Paid tools (names only — details in `tools`) |
| `free_tech` | Free tools relied on |
| `email_addresses` | Brand emails in use |
| `crm` | CRM in use |
| `analytics` | Analytics stack |
| `keywords` | Keywords you rank / bid on |

### kpis
| Field | Meaning |
|---|---|
| `main_kpis` | The numbers you actually watch |
| `call_conversion_value` | $ value of a booked call |
| `dm_conversion_value` | $ value of a DM lead |
| `lead_form_conversion_value` | $ value of a form fill |

### `extra_context`
Free text — anything the structure didn't ask for.

---

## tools[] — one record per tool / affiliate program

### identity
| Field | Meaning |
|---|---|
| `name` | Company/app name (e.g. Opus Pro) |
| `category` | One of the fixed categories (see README) |
| `homepage` | Marketing homepage URL |
| `rating` | Your rating 0–10 |
| `still_relevant` | yes / no — still belongs in the stack? |
| `necessity_pct` | % necessity for the average person, 0–100 |
| `learned_pct` | % of the app you've actually learned, 0–100 |
| `profile_complete` | yes / no — is your in-app profile fully built out? |

### account
| Field | Meaning |
|---|---|
| `login_url` | Where you sign in |
| `email` | Account email |
| `username` | Account username/handle |
| `credential_ref` | Password-manager entry name. **Not the password.** |

### affiliate
| Field | Meaning |
|---|---|
| `link` | Your public referral link |
| `network` | Program platform (CJ, Impact, in-house, …) |
| `application_page` | Where to apply |
| `dashboard_url` | Affiliate portal login/dashboard |
| `email` / `username` | Affiliate-account identity (if different from app account) |
| `payout_terms` | Schedule, %, conditions, bonuses |
| `pending_payout_usd` | Currently pending payout (USD) |
| `coupon_codes` | Codes you can hand out |
| `swipes_media_url` | Link to provided email swipes / media kit |
| `allows_contact_downloads` | yes / no — can you export referred contacts? |

### api
| Field | Meaning |
|---|---|
| `has_api` | yes / no |
| `free` | yes / no — $0 tier exists |
| `rate_limits` | Free/paid limits in one line |
| `access_page` | Where keys are managed |
| `key_ref` | Password-manager entry name for the key. **Not the key.** |

### apps
`ios`, `mac`, `android`, `windows` — download links per platform (blank = no app).

### facts
| Field | Meaning |
|---|---|
| `requires_kyc` | yes / no |
| `works_outside_us` | yes / no / notes |
| `free_trial` | Trial/free tier and its length |
| `usage_limits` | Free vs paid limits |
| `key_features` | Tech / features / difficulty / main value, one line each |

### contact
`support_emails`, `phones`, `ceo_link` — company contact points.

### `notes`
Free text per record.
