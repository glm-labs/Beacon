"""Contact fields an SSO provider can fill from identity-provider claims.

Each provider setting names the claim to read for one user contact field,
the same way ``phone_claim`` does for the phone number. An empty setting
means the field is never read from the identity provider.
"""

# provider setting -> user field it fills
CONTACT_CLAIM_SETTINGS = {
    "telegram_user_id_claim": "telegram_user_id",
    "slack_user_id_claim": "slack_user_id",
    "mattermost_user_id_claim": "mattermost_user_id",
    "pushover_user_key_claim": "pushover_user_key",
}

CONTACT_CLAIM_MAX_LENGTH = 128
