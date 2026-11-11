# JGA Stripe Payment Intent - CORRECTED version of the pasted Step 31.
# Fixes vs the paste:
#  1. [string]$amount * 100 is broken in PowerShell (string * int repeats
#     the string, then [int] cast fails). Amount is now [decimal] and
#     converted with [Math]::Round($amount * 100).
#  2. Amount validated: must be > 0, max $10,000 per call (safety cap).
#  3. automatic_payment_methods enabled - a bare PaymentIntent with no
#     payment method and no payment_method_types cannot be confirmed.
#  4. Errors are surfaced, not swallowed. No key is baked in here.
# SECURITY: do NOT paste a live secret key into config.json in plain
# text. Preferred: complete the Stripe OAuth connect (Jaysgraphicarts
# @gmail.com, already authorized by John 2026-11-02, not yet completed).
# If you must use a key locally: use a TEST key (sk_test_...) first, put
# it in an environment variable, and never commit config.json.
# Creating a PaymentIntent is NOT a cleared payment. Brick 1's 35/65
# gates still require Stripe to show the payment as SUCCEEDED before
# any production or delivery step, and 11VT splits only on cleared money.
param(
    [decimal]$amount,
    [string]$description = "JGA Payment"
)

if ($amount -le 0 -or $amount -gt 10000) {
    throw "Amount must be greater than 0 and no more than 10000."
}

$ConfigPath = Join-Path $PSScriptRoot "config.json"
if (-not (Test-Path $ConfigPath)) { throw "Stripe config not found: $ConfigPath" }
$Config = Get-Content $ConfigPath -Raw | ConvertFrom-Json

# Env var wins over the file, so a key never has to sit in config.json.
$SecretKey = $env:STRIPE_SECRET_KEY
if (-not $SecretKey) { $SecretKey = $Config.SecretKey }
if (-not $SecretKey) { throw "Stripe Secret Key missing. Set STRIPE_SECRET_KEY or fill config.json (test key first)." }
if ($SecretKey -notlike "sk_test_*" -and $SecretKey -notlike "sk_live_*") {
    throw "Secret key does not look like a Stripe secret key (expected sk_test_ or sk_live_). Refusing to call Stripe."
}
if ($SecretKey -like "sk_live_*" -and $env:STRIPE_ALLOW_LIVE -ne "1") {
    throw "Live key detected but STRIPE_ALLOW_LIVE is not 1. Use a test key first."
}

$body = @{
    "amount"                              = [int][Math]::Round($amount * 100)
    "currency"                            = "usd"
    "description"                         = $description
    "automatic_payment_methods[enabled]" = "true"
}

try {
    $response = Invoke-RestMethod `
        -Uri "https://api.stripe.com/v1/payment_intents" `
        -Method Post `
        -Headers @{ Authorization = "Bearer $SecretKey" } `
        -Body $body
    $response | ConvertTo-Json -Depth 10
} catch {
    $err = $_.ErrorDetails.Message
    if (-not $err) { $err = $_.Exception.Message }
    throw "Stripe call failed: $err"
}
