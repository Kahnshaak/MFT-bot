// MongoDB initialization script for gamenight_bot database

// Switch to the gamenight_bot database
db = db.getSiblingDB('gamenight_bot');

// Create collections with validation
db.createCollection('events', {
    validator: {
        $jsonSchema: {
            bsonType: "object",
            required: ["guild_id", "title", "creator_id", "state", "created_at"],
            properties: {
                guild_id: { bsonType: "string" },
                title: { bsonType: "string" },
                creator_id: { bsonType: "string" },
                state: { 
                    enum: ["DRAFT", "DATE_POLLING", "TIME_POLLING", "GAME_POLLING", "SCHEDULED", "COMPLETED", "CANCELLED"]
                },
                created_at: { bsonType: "date" }
            }
        }
    }
});

db.createCollection('users', {
    validator: {
        $jsonSchema: {
            bsonType: "object",
            required: ["user_id", "guild_id"],
            properties: {
                user_id: { bsonType: "string" },
                guild_id: { bsonType: "string" }
            }
        }
    }
});

db.createCollection('recurring_schedules');
db.createCollection('game_interests');
db.createCollection('notifications');
db.createCollection('guild_configs');
db.createCollection('audit_logs');

// Create indexes for optimal performance
db.events.createIndex({ "guild_id": 1, "state": 1, "created_at": -1 });
db.events.createIndex({ "guild_id": 1, "discord_event_id": 1 });
db.events.createIndex({ "guild_id": 1, "schedule.selected_date": 1 });

db.users.createIndex({ "user_id": 1, "guild_id": 1 }, { unique: true });
db.users.createIndex({ "guild_id": 1, "game_interests": 1 });

db.notifications.createIndex({ "scheduled_for": 1, "processed": 1 });
db.notifications.createIndex({ "guild_id": 1, "user_id": 1 });

db.recurring_schedules.createIndex({ "guild_id": 1, "status.is_active": 1 });
db.recurring_schedules.createIndex({ "status.next_trigger": 1 });

db.game_interests.createIndex({ "guild_id": 1, "game_name": 1 });
db.game_interests.createIndex({ "user_id": 1, "guild_id": 1 });

db.guild_configs.createIndex({ "guild_id": 1 }, { unique: true });

db.audit_logs.createIndex({ "guild_id": 1, "timestamp": -1 });
db.audit_logs.createIndex({ "action_type": 1, "timestamp": -1 });

print("Database initialization completed successfully");