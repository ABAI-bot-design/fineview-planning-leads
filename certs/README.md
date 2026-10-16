# Extra intermediate certificates

Some council servers send only their own certificate and leave out the intermediate,
so Python can't verify them (`unable to get local issuer certificate`). Browsers hide
this by fetching the intermediate themselves; `requests` doesn't.

Every `*.pem` here is appended to certifi's bundle in `src/idox.py`. Verification stays on.

| File | Used by | Signed by | Expires | SHA-256 |
|---|---|---|---|---|
| RapidSSLTLSRSACAG1.pem | Hertsmere (www6.hertsmere.gov.uk) | DigiCert Global Root G2 | 2 Nov 2027 | 44:22:E9:63:…:BC:AD:C6:9B |

To add one: take the `CA Issuers` URL from the site's certificate
(`openssl s_client -connect HOST:443 | openssl x509 -noout -text | grep -A2 "Authority Information"`),
convert it with `openssl x509 -inform DER -in X.crt -out X.pem`, and check it with
`openssl verify -CAfile "$(python -c 'import certifi;print(certifi.where())')" X.pem`.
Only add public CA intermediates. Replace this one before Nov 2027.
