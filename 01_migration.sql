-- ============================================================
-- MIGRATION: Team-Based Productivity Rules
-- Adapted for existing teams table with String(36) UUID IDs
-- ============================================================

-- 1. Create the team_app_rules table
CREATE TABLE IF NOT EXISTS team_app_rules (
    id SERIAL PRIMARY KEY,
    team_id VARCHAR(36) NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    app_pattern VARCHAR(255) NOT NULL,
    match_type VARCHAR(20) DEFAULT 'contains',
    category VARCHAR(20) NOT NULL DEFAULT 'neutral',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(team_id, app_pattern)
);

-- 2. Create indexes
CREATE INDEX IF NOT EXISTS idx_team_app_rules_team ON team_app_rules(team_id);
CREATE INDEX IF NOT EXISTS idx_team_app_rules_category ON team_app_rules(category);

-- 3. Insert the 3 teams (UUID string IDs)
INSERT INTO teams (id, name) VALUES
    ('t-yutori-0001-0001-000000000001', 'Yutori'),
    ('t-robotics-001-0001-000000000001', 'Robotics'),
    ('t-smartmfg-001-0001-000000000001', 'Smart Manufacturing')
ON CONFLICT (id) DO NOTHING;

-- 4. Seed default productivity rules
DO $$
DECLARE
    yutori_id VARCHAR(36);
    robotics_id VARCHAR(36);
    smart_mfg_id VARCHAR(36);
BEGIN
    SELECT id INTO yutori_id FROM teams WHERE name = 'Yutori' LIMIT 1;
    SELECT id INTO robotics_id FROM teams WHERE name = 'Robotics' LIMIT 1;
    SELECT id INTO smart_mfg_id FROM teams WHERE name = 'Smart Manufacturing' LIMIT 1;

    -- ========== YUTORI RULES ==========
    INSERT INTO team_app_rules (team_id, app_pattern, category) VALUES
        (yutori_id, 'H2H', 'productive'),
        (yutori_id, 'Google Sheets', 'productive'),
        (yutori_id, 'Sheets', 'productive'),
        (yutori_id, 'Encord', 'productive'),
        (yutori_id, 'Admin Annotation', 'productive'),
        (yutori_id, 'Annotation Panel', 'productive'),
        (yutori_id, 'ChatGPT', 'productive'),
        (yutori_id, 'Slack', 'productive'),
        (yutori_id, 'Google Meet', 'productive'),
        (yutori_id, 'meet.google.com', 'productive')
    ON CONFLICT (team_id, app_pattern) DO NOTHING;

    INSERT INTO team_app_rules (team_id, app_pattern, category) VALUES
        (yutori_id, 'YouTube', 'non_productive'),
        (yutori_id, 'Netflix', 'non_productive'),
        (yutori_id, 'Instagram', 'non_productive'),
        (yutori_id, 'Facebook', 'non_productive'),
        (yutori_id, 'Twitter', 'non_productive'),
        (yutori_id, 'Reddit', 'non_productive')
    ON CONFLICT (team_id, app_pattern) DO NOTHING;

    -- ========== ROBOTICS RULES ==========
    INSERT INTO team_app_rules (team_id, app_pattern, category) VALUES
        (robotics_id, 'Encord', 'productive'),
        (robotics_id, 'Guideline', 'productive'),
        (robotics_id, 'Google Sheets', 'productive'),
        (robotics_id, 'Sheets', 'productive'),
        (robotics_id, 'Slack', 'productive'),
        (robotics_id, 'Google Meet', 'productive'),
        (robotics_id, 'meet.google.com', 'productive'),
        (robotics_id, 'Google Docs', 'productive'),
        (robotics_id, 'Docs', 'productive')
    ON CONFLICT (team_id, app_pattern) DO NOTHING;

    INSERT INTO team_app_rules (team_id, app_pattern, category) VALUES
        (robotics_id, 'YouTube', 'non_productive'),
        (robotics_id, 'Netflix', 'non_productive'),
        (robotics_id, 'Instagram', 'non_productive'),
        (robotics_id, 'Facebook', 'non_productive'),
        (robotics_id, 'Twitter', 'non_productive'),
        (robotics_id, 'Reddit', 'non_productive')
    ON CONFLICT (team_id, app_pattern) DO NOTHING;

    -- ========== SMART MANUFACTURING RULES ==========
    INSERT INTO team_app_rules (team_id, app_pattern, category) VALUES
        (smart_mfg_id, 'Python', 'productive'),
        (smart_mfg_id, 'python', 'productive'),
        (smart_mfg_id, 'VSCode', 'productive'),
        (smart_mfg_id, 'Visual Studio Code', 'productive'),
        (smart_mfg_id, 'Code', 'productive'),
        (smart_mfg_id, 'ChatGPT', 'productive'),
        (smart_mfg_id, 'Claude', 'productive'),
        (smart_mfg_id, 'claude.ai', 'productive'),
        (smart_mfg_id, 'Terminal', 'productive'),
        (smart_mfg_id, 'PowerShell', 'productive'),
        (smart_mfg_id, 'cmd.exe', 'productive'),
        (smart_mfg_id, 'GitHub', 'productive'),
        (smart_mfg_id, 'Jupyter', 'productive'),
        (smart_mfg_id, 'Slack', 'productive')
    ON CONFLICT (team_id, app_pattern) DO NOTHING;

    INSERT INTO team_app_rules (team_id, app_pattern, category) VALUES
        (smart_mfg_id, 'YouTube', 'non_productive'),
        (smart_mfg_id, 'Netflix', 'non_productive'),
        (smart_mfg_id, 'Instagram', 'non_productive'),
        (smart_mfg_id, 'Facebook', 'non_productive'),
        (smart_mfg_id, 'Twitter', 'non_productive'),
        (smart_mfg_id, 'Reddit', 'non_productive')
    ON CONFLICT (team_id, app_pattern) DO NOTHING;

    RAISE NOTICE 'Teams seeded: Yutori=%, Robotics=%, SmartMfg=%', yutori_id, robotics_id, smart_mfg_id;
END $$;
