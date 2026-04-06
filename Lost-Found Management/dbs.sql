
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(120) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    profile_pic VARCHAR(255) DEFAULT 'default.jpg',
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL
);


CREATE TABLE items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    category_id INT,
    image_file VARCHAR(255) DEFAULT 'default.jpg',
    status ENUM('lost', 'found') NOT NULL,
    date DATE NOT NULL,
    user_id INT NOT NULL,
    claimed BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (category_id) REFERENCES categories(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);


CREATE TABLE password_reset_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    otp VARCHAR(6) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);


CREATE TABLE notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    item_id INT NOT NULL,
    message VARCHAR(255) NOT NULL,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (item_id) REFERENCES items(id)
);


CREATE TABLE claimed_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    item_id INT NOT NULL,
    claimer_id INT NOT NULL,
    claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (claimer_id) REFERENCES users(id)
);

ALTER TABLE users
ADD COLUMN roll_number VARCHAR(20) NOT NULL,
ADD COLUMN batch INT NOT NULL,
ADD COLUMN course ENUM('Btech', 'Barch', 'Mtech', 'Msc', 'PHD') NOT NULL,
ADD COLUMN branch ENUM('CSE', 'ECE', 'EEE', 'ICE', 'Chem', 'Civil', 'MECH', 'Prod', 'Other') NOT NULL;


ALTER TABLE items
ADD FOREIGN KEY (user_id) REFERENCES users(id);

ALTER TABLE items
ADD FOREIGN KEY (category_id) REFERENCES categories(id);

ALTER TABLE password_reset_tokens
ADD FOREIGN KEY (user_id) REFERENCES users(id);

ALTER TABLE notifications
ADD FOREIGN KEY (user_id) REFERENCES users(id),
ADD FOREIGN KEY (item_id) REFERENCES items(id);

ALTER TABLE claimed_items
ADD FOREIGN KEY (item_id) REFERENCES items(id),
ADD FOREIGN KEY (claimer_id) REFERENCES users(id);



ALTER TABLE items
ADD COLUMN location VARCHAR(255);



ALTER TABLE users MODIFY COLUMN course ENUM('BTECH', 'BARCH', 'MTECH', 'MSC', 'PHD') NOT NULL;


ALTER TABLE users MODIFY COLUMN branch 
ENUM('CSE', 'ECE', 'EEE', 'EEC', 'ICE', 'CHEM', 'CIVIL', 'MECH', 'PROD', 'OTHER') NOT NULL;

INSERT INTO categories (name) VALUES
  ('ID Card'),
  ('Electronics'),
  ('Books'),
  ('Clothing'),
  ('Accessories'),
  ('Others');


