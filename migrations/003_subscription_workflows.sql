-- Subscription-worker batch tracking and replay-safe claim requests.
-- Apply after the registration schema and migration 002.

CREATE TABLE IF NOT EXISTS batch_runs (
    id UUID PRIMARY KEY,
    batch_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'RUNNING'
        CHECK (status IN ('RUNNING', 'SUCCESS', 'PARTIAL_SUCCESS', 'FAILED')),
    total_customers INTEGER NOT NULL DEFAULT 0 CHECK (total_customers >= 0),
    successful_count INTEGER NOT NULL DEFAULT 0 CHECK (successful_count >= 0),
    failed_count INTEGER NOT NULL DEFAULT 0 CHECK (failed_count >= 0),
    skipped_count INTEGER NOT NULL DEFAULT 0 CHECK (skipped_count >= 0),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    error_message VARCHAR(500)
);

CREATE INDEX IF NOT EXISTS idx_batch_runs_started_at ON batch_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS subscription_claim_requests (
    request_id UUID PRIMARY KEY,
    worker_id VARCHAR(100) NOT NULL,
    workflow_type VARCHAR(50) NOT NULL,
    customer_id UUID,
    workflow_id UUID REFERENCES workflow_runs(id),
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
