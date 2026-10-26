class Lesson {
  final String id;
  final int lessonNumber;
  final String subjectName;
  final String teacherName;
  final String room;
  final String lessonType;
  final int subgroup;
  final String? updatedBy;

  Lesson({required this.id, required this.lessonNumber, required this.subjectName, required this.teacherName, required this.room, required this.lessonType, required this.subgroup, this.updatedBy});

  factory Lesson.fromJson(Map<String, dynamic> json) {
    return Lesson(
      id: json['id'] as String,
      lessonNumber: json['lesson_number'] as int,
      subjectName: json['subject_name'] as String,
      teacherName: json['teacher_name'] as String,
      room: json['room'] as String,
      lessonType: json['lesson_type'] as String,
      subgroup: json['subgroup'] as int,
      updatedBy: json['updated_by'] as String?,
    );
  }
}
