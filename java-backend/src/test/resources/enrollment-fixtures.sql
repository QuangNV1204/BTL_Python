DELETE FROM course_members WHERE course_id IN (6, 7);
DELETE FROM courses WHERE id IN (6, 7);

INSERT INTO courses (id, teacher_id, category_id, title, description, price, is_published, archived_at) VALUES
    (6, 2, 1, 'Khoa free chua ai hoc', 'Mo ta', 0.00, TRUE, NULL),
    (7, 2, 2, 'Khoa tra phi', 'Mo ta', 150000.00, TRUE, NULL);
