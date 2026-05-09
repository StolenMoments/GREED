-- backend-mobile 전용 읽기 전용 MariaDB 계정 생성
-- REPLACE_PASSWORD 를 강력한 패스워드로 교체 후 실행

CREATE USER IF NOT EXISTS 'greed_mobile'@'%' IDENTIFIED BY 'REPLACE_PASSWORD';
GRANT SELECT ON greed.* TO 'greed_mobile'@'%';
FLUSH PRIVILEGES;

-- 확인
SHOW GRANTS FOR 'greed_mobile'@'%';
