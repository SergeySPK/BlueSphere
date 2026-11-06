// Модель для получения уроков
class Lesson {
  final String id;
  final int lessonNumber;
  final String subjectName;
  final String teacherName;
  final String room;
  final String lessonType;
  final int subgroup;
  final String? updatedBy;
  final bool isEditable;
  final bool isEditing;
  final String? editorName;

  Lesson({
    required this.id,
    required this.lessonNumber,
    required this.subjectName,
    required this.teacherName,
    required this.room,
    required this.lessonType,
    required this.subgroup,
    this.updatedBy,
    this.isEditable = false,
    this.isEditing = false,
    this.editorName,
  });

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
      isEditable: json['is_editable'] as bool? ?? false,
      isEditing: json['is_editing'] as bool? ?? false,
      editorName: json['editor_name'] as String?,
    );
  }
}
