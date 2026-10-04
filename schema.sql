-- =====================================================================
-- Job Application Tracker - Database Creation Script
-- COP4751 Advanced Database Management - Course Project
--
-- Run this file to (re)create the entire database with sample data:
--     mysql -u root -p < schema.sql
--
-- WARNING: this DROPS the existing job_app_tracker database first.
-- =====================================================================

DROP DATABASE IF EXISTS job_app_tracker;
CREATE DATABASE job_app_tracker
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
USE job_app_tracker;

-- ---------------------------------------------------------------------
-- 1. companies: organizations you are applying to
-- ---------------------------------------------------------------------
CREATE TABLE companies (
    company_id    INT           PRIMARY KEY AUTO_INCREMENT,
    company_name  VARCHAR(100)  NOT NULL,
    industry      VARCHAR(50),
    website       VARCHAR(200),
    city          VARCHAR(50),
    state         VARCHAR(50),
    notes         TEXT,
    CONSTRAINT uq_company_name UNIQUE (company_name)
);

-- ---------------------------------------------------------------------
-- 2. jobs: specific openings at a company
--    requirements is a JSON array of skill strings,
--    e.g. ["Python", "SQL", "Flask"]
--    Deleting a company deletes its jobs (ON DELETE CASCADE).
-- ---------------------------------------------------------------------
CREATE TABLE jobs (
    job_id        INT           PRIMARY KEY AUTO_INCREMENT,
    company_id    INT           NOT NULL,
    job_title     VARCHAR(100)  NOT NULL,
    job_type      ENUM('Full-time','Part-time','Contract','Internship')
                                NOT NULL DEFAULT 'Full-time',
    salary_min    INT,
    salary_max    INT,
    job_url       VARCHAR(300),
    date_posted   DATE,
    requirements  JSON,
    CONSTRAINT fk_jobs_company
        FOREIGN KEY (company_id) REFERENCES companies(company_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT chk_salary_min_positive CHECK (salary_min IS NULL OR salary_min >= 0),
    CONSTRAINT chk_salary_range CHECK (
        salary_min IS NULL OR salary_max IS NULL OR salary_max >= salary_min),
    CONSTRAINT chk_requirements_is_array CHECK (
        requirements IS NULL OR JSON_TYPE(requirements) = 'ARRAY')
);

-- ---------------------------------------------------------------------
-- 3. applications: your application to a specific job
--    interview_data is a JSON object holding a list of interview rounds:
--    {"rounds": [{"date": "2026-10-01", "type": "Technical",
--                 "interviewer": "Jane Doe", "notes": "..."}]}
--    Deleting a job deletes its applications (ON DELETE CASCADE).
-- ---------------------------------------------------------------------
CREATE TABLE applications (
    application_id    INT          PRIMARY KEY AUTO_INCREMENT,
    job_id            INT          NOT NULL,
    application_date  DATE         NOT NULL,
    status            ENUM('Applied','Screening','Interview','Offer','Rejected','Withdrawn')
                                   NOT NULL DEFAULT 'Applied',
    resume_version    VARCHAR(50),
    cover_letter_sent BOOLEAN      NOT NULL DEFAULT FALSE,
    interview_data    JSON,
    CONSTRAINT fk_applications_job
        FOREIGN KEY (job_id) REFERENCES jobs(job_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT chk_interview_data_is_object CHECK (
        interview_data IS NULL OR JSON_TYPE(interview_data) = 'OBJECT')
);

CREATE INDEX idx_applications_status ON applications(status);
CREATE INDEX idx_applications_date   ON applications(application_date);

-- ---------------------------------------------------------------------
-- 4. contacts: people you know at a company (recruiters, engineers...)
--    Deleting a company keeps the contact but clears the link
--    (ON DELETE SET NULL) - you still know the person.
-- ---------------------------------------------------------------------
CREATE TABLE contacts (
    contact_id    INT           PRIMARY KEY AUTO_INCREMENT,
    company_id    INT,
    contact_name  VARCHAR(100)  NOT NULL,
    title         VARCHAR(100),
    email         VARCHAR(100),
    phone         VARCHAR(20),
    linkedin_url  VARCHAR(200),
    notes         TEXT,
    CONSTRAINT fk_contacts_company
        FOREIGN KEY (company_id) REFERENCES companies(company_id)
        ON DELETE SET NULL ON UPDATE CASCADE
);

-- ---------------------------------------------------------------------
-- View: every application joined to its job and company.
-- Used by the Applications list, detail page and dashboard.
-- ---------------------------------------------------------------------
CREATE VIEW application_details AS
SELECT a.application_id,
       a.job_id,
       a.application_date,
       a.status,
       a.resume_version,
       a.cover_letter_sent,
       a.interview_data,
       j.job_title,
       j.job_type,
       c.company_id,
       c.company_name
FROM applications a
JOIN jobs      j ON j.job_id     = a.job_id
JOIN companies c ON c.company_id = j.company_id;

-- =====================================================================
-- SAMPLE DATA (fictional companies and people)
-- Dates are relative to CURDATE() so the dashboard always shows
-- recent applications and upcoming interviews.
-- =====================================================================

INSERT INTO companies (company_name, industry, website, city, state, notes) VALUES
('Northwind Analytics',   'Data & Analytics', 'https://northwind-analytics.example.com', 'Orlando',   'FL', 'Mid-size analytics consultancy. Hybrid schedule.'),
('Brightpath Health',     'Healthcare',       'https://brightpath-health.example.com',   'Tampa',     'FL', 'Hospital network building an internal software team.'),
('Coastal Cloud Systems', 'Cloud Computing',  'https://coastalcloud.example.com',        'Miami',     'FL', 'Fast-growing startup, fully remote options.'),
('Pixelforge Studios',    'Software',         'https://pixelforge.example.com',          'Austin',    'TX', 'Builds web apps for game studios.'),
('Summit Financial Group','Finance',          'https://summitfinancial.example.com',     'Charlotte', 'NC', 'Large bank; long hiring process.'),
('GreenLeaf Logistics',   'Logistics',        'https://greenleaf-logistics.example.com', 'Atlanta',   'GA', 'Met their recruiter at the campus career fair.');

INSERT INTO jobs (company_id, job_title, job_type, salary_min, salary_max, job_url, date_posted, requirements) VALUES
(1, 'Data Analyst',                  'Full-time',  65000,  80000, 'https://northwind-analytics.example.com/careers/101', CURDATE() - INTERVAL 30 DAY, JSON_ARRAY('Python', 'SQL', 'Tableau')),
(1, 'Junior Data Engineer',          'Full-time',  75000,  95000, 'https://northwind-analytics.example.com/careers/102', CURDATE() - INTERVAL 12 DAY, JSON_ARRAY('Python', 'SQL', 'Airflow', 'AWS')),
(2, 'Software Developer',            'Full-time',  80000, 100000, 'https://brightpath-health.example.com/jobs/sd-1',     CURDATE() - INTERVAL 25 DAY, JSON_ARRAY('Python', 'SQL', 'Flask')),
(2, 'IT Support Intern',             'Internship', 38000,  42000, 'https://brightpath-health.example.com/jobs/it-int',   CURDATE() - INTERVAL 20 DAY, JSON_ARRAY('Windows', 'Networking', 'Customer Service')),
(3, 'Cloud Engineer',                'Full-time',  95000, 120000, 'https://coastalcloud.example.com/jobs/ce',            CURDATE() - INTERVAL 22 DAY, JSON_ARRAY('AWS', 'Linux', 'Terraform', 'Python')),
(3, 'Database Administrator',        'Contract',   85000, 105000, 'https://coastalcloud.example.com/jobs/dba',           CURDATE() - INTERVAL 9 DAY,  JSON_ARRAY('MySQL', 'SQL', 'Linux', 'Backup and Recovery')),
(4, 'Full Stack Developer',          'Full-time',  85000, 110000, 'https://pixelforge.example.com/careers/fsd',          CURDATE() - INTERVAL 28 DAY, JSON_ARRAY('JavaScript', 'React', 'Python', 'SQL', 'Git')),
(4, 'QA Tester',                     'Part-time',  30000,  40000, 'https://pixelforge.example.com/careers/qa',           CURDATE() - INTERVAL 35 DAY, JSON_ARRAY('Selenium', 'Python', 'Git')),
(5, 'Business Intelligence Analyst', 'Full-time',  70000,  88000, 'https://summitfinancial.example.com/careers/bi',      CURDATE() - INTERVAL 15 DAY, JSON_ARRAY('SQL', 'Power BI', 'Excel')),
(6, 'Backend Developer Intern',      'Internship', 35000,  42000, 'https://greenleaf-logistics.example.com/jobs/be-int', CURDATE() - INTERVAL 10 DAY, JSON_ARRAY('Python', 'Flask', 'MySQL', 'Git')),
(6, 'Operations Analyst',            'Full-time',  NULL,   NULL,  NULL,                                                  CURDATE() - INTERVAL 4 DAY,  JSON_ARRAY('Excel', 'SQL'));

INSERT INTO applications (job_id, application_date, status, resume_version, cover_letter_sent, interview_data) VALUES
(1,  CURDATE() - INTERVAL 21 DAY, 'Interview', 'v2-data', TRUE,
     JSON_OBJECT('rounds', JSON_ARRAY(
        JSON_OBJECT('date', DATE_FORMAT(CURDATE() - INTERVAL 10 DAY, '%Y-%m-%d'), 'type', 'Phone Screen', 'interviewer', 'Maria Lopez', 'notes', 'Went well; asked about SQL joins.'),
        JSON_OBJECT('date', DATE_FORMAT(CURDATE() + INTERVAL 3 DAY,  '%Y-%m-%d'), 'type', 'Technical',    'interviewer', 'David Chen',  'notes', 'Prepare a Tableau dashboard demo.')))),
(3,  CURDATE() - INTERVAL 18 DAY, 'Offer', 'v3-dev', TRUE,
     JSON_OBJECT('rounds', JSON_ARRAY(
        JSON_OBJECT('date', DATE_FORMAT(CURDATE() - INTERVAL 12 DAY, '%Y-%m-%d'), 'type', 'Phone Screen', 'interviewer', 'Priya Patel', 'notes', 'Recruiter call.'),
        JSON_OBJECT('date', DATE_FORMAT(CURDATE() - INTERVAL 6 DAY,  '%Y-%m-%d'), 'type', 'Onsite',       'interviewer', 'Team panel',  'notes', 'Built a small Flask API live.')))),
(5,  CURDATE() - INTERVAL 14 DAY, 'Screening', 'v2-cloud', FALSE,
     JSON_OBJECT('rounds', JSON_ARRAY(
        JSON_OBJECT('date', DATE_FORMAT(CURDATE() + INTERVAL 5 DAY, '%Y-%m-%d'), 'type', 'Phone Screen', 'interviewer', 'Alex Rivera', 'notes', 'Review AWS basics.')))),
(7,  CURDATE() - INTERVAL 12 DAY, 'Rejected', 'v3-dev', TRUE,
     JSON_OBJECT('rounds', JSON_ARRAY(
        JSON_OBJECT('date', DATE_FORMAT(CURDATE() - INTERVAL 5 DAY, '%Y-%m-%d'), 'type', 'Technical', 'interviewer', 'Sam Okafor', 'notes', 'Need more React practice.')))),
(9,  CURDATE() - INTERVAL 10 DAY, 'Applied', 'v2-data', FALSE, NULL),
(10, CURDATE() - INTERVAL 7 DAY,  'Interview', 'v3-dev', TRUE,
     JSON_OBJECT('rounds', JSON_ARRAY(
        JSON_OBJECT('date', DATE_FORMAT(CURDATE() + INTERVAL 7 DAY, '%Y-%m-%d'), 'type', 'Behavioral', 'interviewer', 'Kim Nguyen', 'notes', 'Prepare STAR stories.')))),
(6,  CURDATE() - INTERVAL 5 DAY,  'Applied', 'v1-dba', FALSE, NULL),
(8,  CURDATE() - INTERVAL 30 DAY, 'Withdrawn', 'v1', FALSE, NULL),
(2,  CURDATE() - INTERVAL 3 DAY,  'Applied', 'v2-data', TRUE, NULL);

INSERT INTO contacts (company_id, contact_name, title, email, phone, linkedin_url, notes) VALUES
(1, 'Maria Lopez',  'Technical Recruiter',     'maria.lopez@example.com',  '407-555-0101', 'https://www.linkedin.com/in/example-maria', 'Very responsive over email.'),
(1, 'David Chen',   'Senior Data Analyst',     'david.chen@example.com',   '407-555-0102', NULL, 'Will run my technical interview.'),
(2, 'Priya Patel',  'HR Coordinator',          'priya.patel@example.com',  '813-555-0103', 'https://www.linkedin.com/in/example-priya', 'Sent the offer letter.'),
(3, 'Alex Rivera',  'Talent Acquisition Lead', 'alex.rivera@example.com',  '305-555-0104', NULL, NULL),
(4, 'Sam Okafor',   'Engineering Manager',     'sam.okafor@example.com',   '512-555-0105', 'https://www.linkedin.com/in/example-sam', 'Gave helpful feedback after rejection.'),
(6, 'Kim Nguyen',   'Campus Recruiter',        'kim.nguyen@example.com',   '404-555-0106', NULL, 'Met at the fall career fair.'),
(5, 'Jordan Blake', 'Alumni Mentor',           'jordan.blake@example.com', NULL,           'https://www.linkedin.com/in/example-jordan', 'Alumni from my program; offered a referral.');

-- =====================================================================
-- SAMPLE DATA, PART 2: data from my earlier MySQL Workbench assignments
-- (Tech Solutions, Data Analytics Corp, etc.), converted to this schema:
--   * website gets https://            * status mapped to the ENUM values
--   * first_name + last_name -> contact_name, job_title -> title
--   * each job gets a requirements JSON array so Job Match can use it
--   * rows are linked by name lookups, not hard-coded IDs, so this block
--     works no matter how many rows come before it
-- =====================================================================

INSERT INTO companies (company_name, industry, website, city, state, notes) VALUES
('Tech Solutions Inc',  'Technology',      'https://www.techsolutions.com',      'Miami',         'Florida',       NULL),
('Data Analytics Corp', 'Data Science',    'https://www.dataanalytics.com',      'Austin',        'Texas',         NULL),
('Cloud Systems LLC',   'Cloud Computing', 'https://www.cloudsystems.com',       'Seattle',       'Washington',    NULL),
('Digital Innovations', 'Software',        'https://www.digitalinnovations.com', 'San Francisco', 'California',
    CONCAT('Applied to Senior Developer position on ', CURDATE())),
('Smart Tech Group',    'AI/ML',           'https://www.smarttech.com',          'Boston',        'Massachusetts', NULL),
('New Tech Corp',       'Technology',      NULL,                                 'Denver',        'Colorado',      NULL);

INSERT INTO jobs (company_id, job_title, job_type, salary_min, salary_max, date_posted, requirements) VALUES
((SELECT company_id FROM companies WHERE company_name = 'Tech Solutions Inc'),  'Software Developer',     'Full-time',  70000,  90000, '2025-01-15', JSON_ARRAY('Python', 'Java', 'SQL', 'Git')),
((SELECT company_id FROM companies WHERE company_name = 'Tech Solutions Inc'),  'Database Administrator', 'Full-time',  75000,  95000, '2025-01-10', JSON_ARRAY('SQL', 'MySQL', 'Linux', 'Backup and Recovery')),
((SELECT company_id FROM companies WHERE company_name = 'Data Analytics Corp'), 'Data Analyst',           'Full-time',  65000,  85000, '2025-01-12', JSON_ARRAY('Python', 'SQL', 'Tableau', 'Excel')),
((SELECT company_id FROM companies WHERE company_name = 'Cloud Systems LLC'),   'Cloud Engineer',         'Full-time',  80000, 100000, '2025-01-08', JSON_ARRAY('AWS', 'Linux', 'Terraform', 'Python')),
((SELECT company_id FROM companies WHERE company_name = 'Digital Innovations'), 'Junior Developer',       'Full-time',  55000,  70000, '2025-01-14', JSON_ARRAY('JavaScript', 'Python', 'Git', 'SQL')),
((SELECT company_id FROM companies WHERE company_name = 'Digital Innovations'), 'Senior Developer',       'Full-time',  95000, 120000, '2025-01-14', JSON_ARRAY('Python', 'JavaScript', 'React', 'SQL', 'AWS')),
((SELECT company_id FROM companies WHERE company_name = 'Smart Tech Group'),    'ML Engineer',            'Full-time',  90000, 115000, '2025-01-11', JSON_ARRAY('Python', 'Machine Learning', 'TensorFlow', 'SQL')),
((SELECT company_id FROM companies WHERE company_name = 'Tech Solutions Inc'),  'QA Engineer',            'Full-time',  60000,  80000, '2025-01-05', JSON_ARRAY('Selenium', 'Python', 'Git')),
((SELECT company_id FROM companies WHERE company_name = 'Data Analytics Corp'), 'Business Analyst',       'Full-time',  65000,  85000, '2025-01-06', JSON_ARRAY('SQL', 'Excel', 'Power BI')),
((SELECT company_id FROM companies WHERE company_name = 'Data Analytics Corp'), 'Data Scientist',         'Full-time',  85000, 110000, '2025-01-07', JSON_ARRAY('Python', 'SQL', 'Machine Learning', 'Statistics')),
((SELECT company_id FROM companies WHERE company_name = 'Cloud Systems LLC'),   'DevOps Engineer',       'Full-time',  80000, 105000, '2025-01-08', JSON_ARRAY('AWS', 'Linux', 'Docker', 'Git')),
((SELECT company_id FROM companies WHERE company_name = 'Cloud Systems LLC'),   'Security Analyst',       'Full-time',  75000,  95000, '2025-01-09', JSON_ARRAY('Networking', 'Linux', 'Python')),
((SELECT company_id FROM companies WHERE company_name = 'Digital Innovations'), 'UI/UX Designer',         'Full-time',  60000,  80000, '2025-01-10', JSON_ARRAY('Figma', 'HTML', 'CSS')),
((SELECT company_id FROM companies WHERE company_name = 'Smart Tech Group'),    'Product Manager',        'Full-time',  90000, 120000, '2025-01-11', JSON_ARRAY('Agile', 'Communication', 'SQL')),
((SELECT company_id FROM companies WHERE company_name = 'Tech Solutions Inc'),  'Technical Writer',       'Contract',   55000,  75000, '2025-01-12', JSON_ARRAY('Documentation', 'Git', 'Communication')),
((SELECT company_id FROM companies WHERE company_name = 'Data Analytics Corp'), 'Intern - Data',          'Internship', 30000,  40000, '2025-01-13', JSON_ARRAY('Python', 'SQL', 'Excel')),
((SELECT company_id FROM companies WHERE company_name = 'Digital Innovations'), 'Intern - Development',   'Internship', 32000,  42000, '2025-01-14', JSON_ARRAY('Python', 'Git', 'HTML', 'CSS')),
((SELECT company_id FROM companies WHERE company_name = 'New Tech Corp'),      'Software Architect',     'Full-time', 120000, 150000, NULL,         JSON_ARRAY('Python', 'AWS', 'SQL', 'System Design'));

-- Statuses mapped to the ENUM: 'Interview Scheduled' -> Interview, 'Phone Screen' -> Screening
INSERT INTO applications (job_id, application_date, status, resume_version, cover_letter_sent) VALUES
((SELECT j.job_id FROM jobs j JOIN companies c USING (company_id) WHERE c.company_name = 'Tech Solutions Inc'  AND j.job_title = 'Software Developer'), '2025-01-16', 'Applied',   'v2.1', TRUE),
((SELECT j.job_id FROM jobs j JOIN companies c USING (company_id) WHERE c.company_name = 'Data Analytics Corp' AND j.job_title = 'Data Analyst'),       '2025-01-13', 'Interview', 'v2.1', TRUE),
((SELECT j.job_id FROM jobs j JOIN companies c USING (company_id) WHERE c.company_name = 'Cloud Systems LLC'   AND j.job_title = 'Cloud Engineer'),      '2025-01-09', 'Rejected',  'v2.0', FALSE),
((SELECT j.job_id FROM jobs j JOIN companies c USING (company_id) WHERE c.company_name = 'Digital Innovations' AND j.job_title = 'Junior Developer'),    '2025-01-15', 'Applied',   'v2.1', TRUE),
((SELECT j.job_id FROM jobs j JOIN companies c USING (company_id) WHERE c.company_name = 'Smart Tech Group'    AND j.job_title = 'ML Engineer'),          '2025-01-12', 'Screening', 'v2.1', TRUE),
((SELECT j.job_id FROM jobs j JOIN companies c USING (company_id) WHERE c.company_name = 'Cloud Systems LLC'   AND j.job_title = 'Cloud Engineer'),      CURDATE(),   'Applied',   'v3.0', TRUE);

INSERT INTO contacts (company_id, contact_name, title, email) VALUES
((SELECT company_id FROM companies WHERE company_name = 'Tech Solutions Inc'),  'Sarah Johnson',   'HR Manager',          'sjohnson@techsolutions.com'),
((SELECT company_id FROM companies WHERE company_name = 'Data Analytics Corp'), 'Michael Chen',    'Technical Recruiter', 'mchen@dataanalytics.com'),
((SELECT company_id FROM companies WHERE company_name = 'Cloud Systems LLC'),   'Emily Williams',  'Hiring Manager',      'ewilliams@cloudsystems.com'),
((SELECT company_id FROM companies WHERE company_name = 'Digital Innovations'), 'David Brown',     'Senior Developer',    NULL),
((SELECT company_id FROM companies WHERE company_name = 'Smart Tech Group'),    'Lisa Garcia',     'Talent Acquisition',  'lgarcia@smarttech.com'),
((SELECT company_id FROM companies WHERE company_name = 'Digital Innovations'), 'Robert Kim',      'Engineering Manager', 'rkim@digitalinnovations.com');
