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
    ACCOUNT_DOES_NOT_EXIST = 'ACCOUNT_DOES_NOT_EXIST'
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

    MAPPING_KEYS = ("api2_state", "ubiquity_message", "ubiquity_slug", "api2_slug", "api2_description")
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
        REGISTRATION_ASYNC_IN_PROGRESS: (StatusName.PENDING, 'Asynchronous registration in progress',
                                         'REGISTRATION_ASYNC_IN_PROGRESS', Api2Slug.NULL, None),
        # 444
        NO_SUCH_RECORD: (StatusName.FAILED, 'No user currently found', 'NO_SUCH_RECORD',
                         Api2Slug.ACCOUNT_DOES_NOT_EXIST, 'Account does not exist'),
        # 445
        ACCOUNT_ALREADY_EXISTS: (StatusName.FAILED, 'Account already exists', 'ACCOUNT_ALREADY_EXISTS',
                                 Api2Slug.ACCOUNT_ALREADY_EXISTS, 'An account already exists'),
        # 446
        FAILED_UPDATE: (StatusName.FAILED, 'Update failed. Delete and re-add card.', 'FAILED_UPDATE',
                        Api2Slug.UPDATE_FAILED, 'Update failed, delete and re-add card'),
        # 447
        SCHEME_REQUESTED_DELETE: (StatusName.FAILED, 'The scheme has requested this account should be deleted',
                                  'SCHEME_REQUESTED_DELETE', Api2Slug.AUTHORISATION_EXPIRED,
                                  'Authorisation expired'),
        # 503
        RESOURCE_LIMIT_REACHED: (StatusName.DEPENDANT, 'Too many balance requests running', 'RESOURCE_LIMIT_REACHED'),
        # 520
        UNKNOWN_ERROR: (StatusName.DEPENDANT, 'An unknown error has occurred', 'UNKNOWN_ERROR', Api2Slug.NULL, None),
        # 530
        END_SITE_DOWN: (StatusName.DEPENDANT, 'End site down', 'END_SITE_DOWN', Api2Slug.NULL, None),
        # 531
        IP_BLOCKED: (StatusName.DEPENDANT, 'IP blocked', 'IP_BLOCKED', Api2Slug.NULL, None),
        # 532
        TRIPPED_CAPTCHA: (StatusName.DEPENDANT, 'Tripped captcha', 'TRIPPED_CAPTCHA', Api2Slug.NULL, None),
        # 533
        PASSWORD_EXPIRED: (StatusName.UNAUTHORISED, 'Password expired', 'PASSWORD_EXPIRED',
                           Api2Slug.AUTHORISATION_EXPIRED, 'Authorisation expired'),
        # 535
        NOT_SENT: (StatusName.DEPENDANT, 'Request was not sent', 'NOT_SENT', Api2Slug.NULL, None),
        # 536
        CONFIGURATION_ERROR: (StatusName.DEPENDANT, 'Error with the configuration or it was not possible to retrieve',
                              'CONFIGURATION_ERROR', Api2Slug.NULL, None),
        # 537
        SERVICE_CONNECTION_ERROR: (StatusName.DEPENDANT, 'Service connection error', 'SERVICE_CONNECTION_ERROR',
                                   Api2Slug.NULL, None),
        # 538
        JOIN_ERROR: (StatusName.DEPENDANT, 'A system error occurred during join', 'JOIN_ERROR', Api2Slug.NULL, None),
        # 900
        JOIN: (StatusName.FAILED, 'Join', 'JOIN', Api2Slug.JOIN_FAILED, 'Join data rejected by merchant'),
        # 901
        ENROL_FAILED: (StatusName.FAILED, 'Enrol Failed', 'ENROL_FAILED',
                       Api2Slug.JOIN_FAILED, 'Join data rejected by merchant'),
        # 902
        REGISTRATION_FAILED: (StatusName.FAILED, 'Ghost Card Registration Failed', 'REGISTRATION_FAILED',
                              Api2Slug.ACCOUNT_NOT_REGISTERED, 'Account not registered')
    }

    AUTH_IN_PROGRESS = [PENDING]
    REGISTRATION_IN_PROGRESS = [PENDING, JOIN_ASYNC_IN_PROGRESS]

    JOIN_PENDING = [JOIN_ASYNC_IN_PROGRESS]
    REGISTER_PENDING = [REGISTRATION_ASYNC_IN_PROGRESS]

    @classmethod
    def get_status_dict(cls, state_code):
        return dict(zip(cls.MAPPING_KEYS, cls.STATUS_MAPPING.get(state_code)))
