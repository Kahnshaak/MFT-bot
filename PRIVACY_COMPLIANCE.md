# Privacy and Compliance Features

This document describes the privacy and compliance features implemented in the Discord Game Night Bot to ensure GDPR compliance and data protection.

## Overview

The bot implements comprehensive privacy and compliance features including:

- **User Consent Management** - Track and manage user consent for data processing
- **Data Export (Right to Data Portability)** - Allow users to export all their data
- **Data Deletion (Right to be Forgotten)** - Allow users to delete all their data
- **Data Retention Policies** - Automatically clean up old data according to policies
- **Privacy Controls** - User-configurable privacy settings
- **Audit Trails** - Complete logging of all data access and modifications
- **Secure Backup and Recovery** - Privacy-compliant backup procedures

## User Commands

### `/privacy settings`
View and update privacy settings:
- `profile_public` - Make profile visible to other users
- `stats_public` - Make statistics visible to other users  
- `allow_game_pings` - Allow game ping notifications
- `allow_notifications` - Allow event notifications
- `allow_analytics` - Allow analytics data collection

### `/privacy consent`
Manage consent for data processing:
- `data_collection` - Consent for basic data collection
- `analytics` - Consent for analytics and statistics
- `notifications` - Consent for notification processing
- `profile_visibility` - Consent for profile visibility
- `data_sharing` - Consent for data sharing with third parties

### `/privacy export`
Request export of all personal data:
- Supports JSON and ZIP formats
- Includes all user data across all collections
- Files expire after 30 days
- Fulfills GDPR right to data portability

### `/privacy export_status`
Check status of data export request:
- Shows processing status
- Provides download information when ready
- Shows expiration date

### `/privacy delete`
Request deletion of all personal data:
- Requires explicit confirmation
- Deletes all personal data permanently
- Keeps anonymized data for analytics
- Fulfills GDPR right to erasure (right to be forgotten)

## Admin Commands

### `/admin_privacy compliance_report`
Generate comprehensive compliance report:
- Data overview and statistics
- Consent status summary
- Data retention status
- Recent privacy requests

### `/admin_privacy cleanup`
Run data retention cleanup policies:
- Applies all active retention policies
- Shows detailed cleanup results
- Can be run manually or automatically

### `/admin_privacy backup`
Create backup of privacy-related data:
- Backs up consent records
- Backs up user privacy settings
- Backs up privacy-related audit logs
- Secure storage with metadata

### `/admin_privacy exports`
View and manage data export requests:
- Filter by status (pending, processing, completed, failed)
- Shows recent export requests
- Management information

### `/admin_privacy retention_settings`
View current data retention settings:
- Shows retention periods for different data types
- Explains automatic cleanup schedule
- Legal compliance information

### `/admin_privacy user_data`
View privacy information for specific user:
- Data summary and statistics
- Privacy settings status
- Consent history
- Recent export requests

## Data Retention Policies

The system implements automatic data retention policies to comply with privacy regulations:

### Default Retention Periods

- **Completed Events**: 365 days (1 year)
- **Cancelled Events**: 90 days (3 months)
- **Processed Notifications**: 30 days (1 month)
- **Inactive Users**: 730 days (2 years) - anonymized
- **Audit Logs**: 2555 days (7 years) - legal requirement
- **Analytics Data**: 1095 days (3 years)

### Retention Actions

- **Delete**: Permanently remove data
- **Anonymize**: Remove personal identifiers but keep data for analytics
- **Archive**: Move to long-term storage (future feature)

### Automatic Cleanup

- Runs daily at midnight UTC
- Can be triggered manually by administrators
- Comprehensive logging of all cleanup actions
- Error handling and recovery

## Consent Management

### Consent Types

1. **Data Collection** - Basic consent for collecting user data
2. **Analytics** - Consent for analytics and usage statistics
3. **Notifications** - Consent for sending notifications
4. **Profile Visibility** - Consent for making profile visible to others
5. **Data Sharing** - Consent for sharing data with third parties

### Consent Features

- **Granular Control** - Users can grant/revoke consent for specific purposes
- **Audit Trail** - All consent changes are logged with timestamps
- **Legal Compliance** - Meets GDPR consent requirements
- **Easy Management** - Simple commands for users to manage consent

## Data Export (Right to Data Portability)

### What's Included

- User profile and preferences
- Events created and participated in
- Game interests and notifications
- Consent history
- Recent audit log entries
- Statistics and analytics data

### Export Formats

- **JSON** - Machine-readable format
- **ZIP** - Compressed archive with README

### Export Process

1. User requests export via `/privacy export`
2. System generates unique request ID
3. Data is collected asynchronously from all collections
4. Export file is generated in requested format
5. User is notified when ready for download
6. Files automatically expire after 30 days

## Data Deletion (Right to be Forgotten)

### What's Deleted

- User profile and preferences
- Personal identifiers from events
- RSVP and attendance records
- Game interests and notifications
- Personal statistics

### What's Preserved

- Anonymized event data (for server analytics)
- Consent records (for legal compliance)
- Audit logs (anonymized for security)

### Deletion Process

1. User requests deletion via `/privacy delete`
2. System shows confirmation dialog with warnings
3. User must explicitly confirm the action
4. All personal data is permanently deleted
5. Some data is anonymized rather than deleted
6. Complete audit trail of deletion is maintained

## Privacy Controls

### User Privacy Settings

- **Profile Public** - Control profile visibility
- **Stats Public** - Control statistics visibility
- **Allow Game Pings** - Control game notification preferences
- **Allow Event Notifications** - Control event notification preferences
- **Allow Analytics Tracking** - Control analytics data collection

### Privacy by Design

- Default settings prioritize user privacy
- Minimal data collection principle
- Purpose limitation - data only used for stated purposes
- Data minimization - only collect necessary data
- Transparency - clear information about data use

## Audit Trails

### What's Logged

- All data access and modifications
- Privacy setting changes
- Consent grants and revocations
- Data export requests and downloads
- Data deletion requests and execution
- Administrative actions

### Audit Features

- **Immutable Logs** - Audit logs cannot be modified
- **Comprehensive Coverage** - All privacy-relevant actions logged
- **Searchable** - Logs can be filtered and searched
- **Long Retention** - Kept for 7 years for legal compliance
- **Secure Storage** - Protected against unauthorized access

## Backup and Recovery

### Privacy Backup Features

- **Selective Backup** - Only privacy-related data
- **Secure Storage** - Encrypted and access-controlled
- **Metadata Tracking** - Complete backup information
- **Automated Cleanup** - Old backups automatically removed

### What's Backed Up

- User consent records
- Privacy settings
- Data export requests
- Privacy-related audit logs

## Legal Compliance

### GDPR Compliance

- **Lawful Basis** - Clear legal basis for all data processing
- **Consent Management** - Granular consent with easy withdrawal
- **Data Subject Rights** - Full implementation of all GDPR rights
- **Data Protection by Design** - Privacy built into system architecture
- **Breach Notification** - Automated alerting for security incidents

### Data Subject Rights

1. **Right to Information** - Clear privacy notices and data use information
2. **Right of Access** - Users can view all their data
3. **Right to Rectification** - Users can correct inaccurate data
4. **Right to Erasure** - Users can delete their data
5. **Right to Restrict Processing** - Users can limit data processing
6. **Right to Data Portability** - Users can export their data
7. **Right to Object** - Users can object to data processing

### Compliance Monitoring

- **Regular Reports** - Automated compliance reporting
- **Policy Enforcement** - Automatic enforcement of retention policies
- **Audit Trails** - Complete audit trails for compliance verification
- **Data Mapping** - Clear mapping of all data flows and processing

## Security Features

### Data Protection

- **Encryption at Rest** - All data encrypted in database
- **Encryption in Transit** - All communications encrypted
- **Access Controls** - Role-based access to privacy features
- **Audit Logging** - All access logged and monitored

### Privacy by Default

- **Minimal Collection** - Only collect necessary data
- **Default Privacy** - Privacy-friendly default settings
- **Purpose Limitation** - Data only used for stated purposes
- **Retention Limits** - Automatic deletion of old data

## Implementation Details

### Core Components

- **PrivacyManager** - Main privacy management system
- **DataRetentionManager** - Handles retention policies
- **ConsentManager** - Manages user consent
- **AuditLogger** - Comprehensive audit logging

### Database Collections

- `user_consent` - User consent records
- `data_export_requests` - Data export requests
- `data_retention_policies` - Retention policy configurations
- `audit_logs` - Privacy-related audit logs

### Background Tasks

- **Daily Cleanup** - Automatic data retention cleanup
- **Export Processing** - Asynchronous data export generation
- **Compliance Monitoring** - Regular compliance checks

## Configuration

### Environment Variables

- `PRIVACY_BACKUP_PATH` - Path for privacy backups
- `DATA_EXPORT_PATH` - Path for data exports
- `RETENTION_CHECK_INTERVAL` - How often to check retention policies

### Retention Policy Configuration

Retention policies can be customized per server:

```python
# Example custom retention policy
policy = RetentionPolicy(
    policy_id="custom_events",
    name="Custom Event Retention",
    description="Delete custom events after 6 months",
    collection="events",
    policy_type=RetentionPolicyType.TIME_BASED,
    action=RetentionAction.DELETE,
    retention_days=180,
    date_field="updated_at",
    conditions={"event_type": "custom"}
)
```

## Monitoring and Alerting

### Privacy Metrics

- Number of active users with consent
- Data export request volume
- Data deletion request volume
- Retention policy execution results
- Compliance report statistics

### Alerts

- Failed data exports
- Failed data deletions
- Retention policy failures
- Unusual privacy request patterns
- Compliance violations

## Testing

Run the privacy system tests:

```bash
python test_privacy_system.py
```

This will test:
- Consent management
- Data export functionality
- Privacy settings
- Data retention policies
- Compliance reporting
- Data deletion

## Support

For privacy-related questions or issues:

1. Check this documentation
2. Review audit logs for specific actions
3. Use compliance reporting for overview
4. Contact system administrators for technical issues

## Future Enhancements

- **Data Portability API** - REST API for data exports
- **Privacy Dashboard** - Web interface for privacy management
- **Advanced Retention Policies** - More complex retention rules
- **Data Classification** - Automatic data sensitivity classification
- **Privacy Impact Assessments** - Automated privacy impact analysis