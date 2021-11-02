class StatusName:
    PENDING = "pending"
    AUTHORISED = "authorised"
    UNAUTHORISED = "unauthorised"
    FAILED = "failed"
    DELETED = "deleted"
    DEPENDANT = AUTHORISED, PENDING


class Api2Slug:
    NULL = None
    WALLET_ONLY = "WALLET_ONLY"

    FAILED_VALIDATION = "FAILED_VALIDATION"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    AUTHORISATION_FAILED = "AUTHORISATION_FAILED"
    AUTHORISATION_EXPIRED = "AUTHORISATION_EXPIRED"
    ACCOUNT_NOT_REGISTERED = "ACCOUNT_NOT_REGISTERED"
    ACCOUNT_ALREADY_EXISTS = "ACCOUNT_ALREADY_EXISTS"

    ADD_FAILED = "ADD_FAILED"
    JOIN_FAILED = "JOIN_FAILED"
    UPDATE_FAILED = "UPDATE_FAILED"
    JOIN_IN_PROGRESS = "JOIN_IN_PROGRESS"


class LoyaltyCardStatus:
    PENDING = 0
    ACTIVE = 1
    INVALID_CREDENTIALS = 403
    INVALID_MFA = 432
    END_SITE_DOWN = 530
    IP_BLOCKED = 531
    TRIPPED_CAPTCHA = 532
    INCOMPLETE = 5
    LOCKED_BY_ENDSITE = 434
    RETRY_LIMIT_REACHED = 429
    RESOURCE_LIMIT_REACHED = 503
    UNKNOWN_ERROR = 520
    MIDAS_UNREACHABLE = 9
    AGENT_NOT_FOUND = 404
    WALLET_ONLY = 10
    PASSWORD_EXPIRED = 533
    JOIN = 900
    NO_SUCH_RECORD = 444
    CONFIGURATION_ERROR = 536
    NOT_SENT = 535
    ACCOUNT_ALREADY_EXISTS = 445
    SERVICE_CONNECTION_ERROR = 537
    VALIDATION_ERROR = 401
    PRE_REGISTERED_CARD = 406
    FAILED_UPDATE = 446
    SCHEME_REQUESTED_DELETE = 447
    PENDING_MANUAL_CHECK = 204
    CARD_NUMBER_ERROR = 436
    LINK_LIMIT_EXCEEDED = 437
    CARD_NOT_REGISTERED = 438
    GENERAL_ERROR = 439
    JOIN_IN_PROGRESS = 441
    JOIN_ERROR = 538
    JOIN_ASYNC_IN_PROGRESS = 442
    REGISTRATION_ASYNC_IN_PROGRESS = 443
    ENROL_FAILED = 901
    REGISTRATION_FAILED = 902

    MAPPING_KEYS = ("api2_state", "ubiguity_message", "ubiguity_slug", "api2_slug", "api2_description")
    STATUS_MAPPING = {
        PENDING: (StatusName.PENDING, 'Pending', 'PENDING', Api2Slug.NULL, None),
        ACTIVE: (StatusName.AUTHORISED, 'Active', 'ACTIVE', Api2Slug.NULL, None),
        INCOMPLETE: (StatusName.UNAUTHORISED, 'Please check your scheme account login details.', 'INCOMPLETE',
                     Api2Slug.AUTHORISATION_FAILED, 'Authorisation data rejected by merchant'),
        MIDAS_UNREACHABLE: ('Midas unavailable', 'MIDAS_UNREACHABLE'),
        WALLET_ONLY: (StatusName.PENDING, 'Wallet only card', 'WALLET_ONLY', Api2Slug.WALLET_ONLY,
                      "No authorisation provided"),
        PENDING_MANUAL_CHECK: (StatusName.PENDING, 'Pending manual check.', 'PENDING_MANUAL_CHECK', Api2Slug.NULL,
                               None),
        VALIDATION_ERROR: (StatusName.FAILED, 'Failed validation', 'VALIDATION_ERROR',
                           Api2Slug.ADD_FAILED, 'Add data rejected by merchant'),
        INVALID_CREDENTIALS: (StatusName.FAILED, 'Invalid credentials', 'INVALID_CREDENTIALS',
                              Api2Slug.AUTHORISATION_FAILED,
                              'Authorisation data rejected by merchant'),
        AGENT_NOT_FOUND: (StatusName.DEPENDANT, 'Agent does not exist on midas', 'AGENT_NOT_FOUND',
                          Api2Slug.NULL, None),
        PRE_REGISTERED_CARD: (StatusName.FAILED, 'Pre-registered card', 'PRE_REGISTERED_CARD',
                              Api2Slug.ACCOUNT_NOT_REGISTERED, 'Account not registered'),
        RETRY_LIMIT_REACHED: (StatusName.DEPENDANT, 'Cannot connect, too many retries', 'RETRY_LIMIT_REACHED',
                              None, None),
        INVALID_MFA: (StatusName.UNAUTHORISED, 'Invalid mfa', 'INVALID_MFA',
                      Api2Slug.AUTHORISATION_FAILED, 'Authorisation data rejected by merchant'),
        LOCKED_BY_ENDSITE: (StatusName.FAILED, 'Account locked on end site', 'LOCKED_BY_ENDSITE',
                            Api2Slug.AUTHORISATION_EXPIRED, 'Authorisation expired'),
        CARD_NUMBER_ERROR: (StatusName.FAILED, 'Invalid card_number', 'CARD_NUMBER_ERROR',
                            Api2Slug.ADD_FAILED, "Add data rejected by merchant"),

        LINK_LIMIT_EXCEEDED: (StatusName.DEPENDANT, 'You can only Link one card per day.', 'LINK_LIMIT_EXCEEDED',
                              Api2Slug.NULL, None),
        CARD_NOT_REGISTERED: (StatusName.FAILED, 'Unknown Card number', 'CARD_NOT_REGISTERED',
                              Api2Slug.ACCOUNT_NOT_REGISTERED, 'Account not registered'),
        GENERAL_ERROR: (StatusName.FAILED, 'General Error such as incorrect user details', 'GENERAL_ERROR',
                        Api2Slug.NULL, None),
        # 441
        JOIN_IN_PROGRESS: (StatusName.FAILED, 'Join in progress', 'JOIN_IN_PROGRESS', Api2Slug.NULL, None),
        # 442
        JOIN_ASYNC_IN_PROGRESS: (StatusName.PENDING, 'Asynchronous join in progress', 'JOIN_ASYNC_IN_PROGRESS',
                                 Api2Slug.JOIN_IN_PROGRESS, None),

        # 443
        REGISTRATION_ASYNC_IN_PROGRESS:  ('Asynchronous registration in progress', 'REGISTRATION_ASYNC_IN_PROGRESS'),

        # 444
        NO_SUCH_RECORD: ('No user currently found', 'NO_SUCH_RECORD'),

        # 445
        ACCOUNT_ALREADY_EXISTS: ('Account already exists', 'ACCOUNT_ALREADY_EXISTS'),

        # 446
        FAILED_UPDATE: ('Update failed. Delete and re-add card.', 'FAILED_UPDATE'),

        # 447
        SCHEME_REQUESTED_DELETE: ('The scheme has requested this account should be deleted', 'SCHEME_REQUESTED_DELETE'),

        # 503
        RESOURCE_LIMIT_REACHED: ('Too many balance requests running', 'RESOURCE_LIMIT_REACHED'),
        # 520
        UNKNOWN_ERROR: ('An unknown error has occurred', 'UNKNOWN_ERROR'),
        # 530
        END_SITE_DOWN: ('End site down', 'END_SITE_DOWN'),

        # 531
        IP_BLOCKED: ('IP blocked', 'IP_BLOCKED'),

        # 532
        TRIPPED_CAPTCHA: ('Tripped captcha', 'TRIPPED_CAPTCHA'),

        # 533
        PASSWORD_EXPIRED: ('Password expired', 'PASSWORD_EXPIRED'),
        # 535
        NOT_SENT: ('Request was not sent', 'NOT_SENT'),

        # 536
        CONFIGURATION_ERROR: ('Error with the configuration or it was not possible to retrieve', 'CONFIGURATION_ERROR'),

        # 537
        SERVICE_CONNECTION_ERROR: ('Service connection error', 'SERVICE_CONNECTION_ERROR'),

        # 538
        JOIN_ERROR: ('A system error occurred during join', 'JOIN_ERROR'),

        # 900
        JOIN: ('Join', 'JOIN'),

        # 901
        ENROL_FAILED: ('Enrol Failed', 'ENROL_FAILED'),

        # 902
        REGISTRATION_FAILED: ('Ghost Card Registration Failed', 'REGISTRATION_FAILED'),


    }

    AUTH_IN_PROGRESS = [PENDING]
    REGISTRATION_IN_PROGRESS = [PENDING, JOIN_ASYNC_IN_PROGRESS]

    JOIN_PENDING = [JOIN_ASYNC_IN_PROGRESS]
    REGISTER_PENDING = [REGISTRATION_ASYNC_IN_PROGRESS]

    @classmethod
    def get_status_dict(cls, state_code):
        return dict(zip(cls.MAPPING_KEYS, cls.STATUS_MAPPING.get(state_code)))

