# Twilio Support Ticket — paste-ready

**Where to file:** Twilio Console → "?" (Help) icon top right → Contact Support →
new ticket. Product: Messaging / A2P 10DLC. Priority: normal.

**Subject:**
Cannot create A2P 10DLC campaign — error 20003 "Policy evaluation failed" on Messaging API + console crash

**Description (paste):**

I am unable to complete US A2P 10DLC campaign registration on my account
(Account SID AC297…(redacted — full SID in Twilio console)).

What works:
- My Customer Profile "Divine Realty" is twilio-approved (BU3c61d142fb4de11099efc7313158b564)
- My A2P Brand is APPROVED / identity VERIFIED (BN9bafbf1e602a0b137fa826e89f298a9a, Low-Volume Standard, registered today)
- Core REST API (api.twilio.com) works normally with my credentials
- Account balance is $33.20 (sufficient for the $15 vetting fee)

What fails:
1. In the Console A2P onboarding wizard, clicking Create → Confirm on the
   campaign step always shows: "Oops! Something went wrong. Cannot destructure
   property 'store' of 'n(...)' as it is null." This happens every time, in the
   legacy wizard inside One Console (my account appears recently migrated to
   the new One Console / organization billing).
2. Direct REST calls to https://messaging.twilio.com/v1/Services (GET or POST)
   return HTTP 401, error 20003 "Policy evaluation failed" — with BOTH my
   account Auth Token and a freshly created standard API Key. The same
   credentials work fine against api.twilio.com.

It looks like a policy/permission problem on the Messaging API for my account,
possibly related to the One Console migration, which also breaks the console
wizard. Please fix the account policy so I can register my Low Volume Mixed
campaign (the campaign details are ready to submit).

**After they fix it:** re-run the campaign creation — all form answers are in
docs/A2P_SOLE_PROP_KIT.md (samples, description, consent text, privacy URL
https://divinerealtyteam.com/privacy-policy, terms URL
https://divinerealtyteam.com/terms-of-use).
