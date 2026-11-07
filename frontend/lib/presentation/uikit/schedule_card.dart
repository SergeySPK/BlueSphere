import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import '../../domain/lesson.dart';
import 'colors.dart';

// Кастомный виджет карточки расписания на день
class ScheduleCard extends StatelessWidget {
  final String day; // Номер дня
  final String month; // Название месяца
  final String weekday; // День недели
  final List<Lesson> lessons;
  final Color statusColor; // Цвет плашки дня
  final Function(Lesson)? onEditLesson; //
  final int? editingLessonNumber; // Номер урока, который редактируем

  const ScheduleCard({super.key, required this.day, required this.month, required this.weekday, required this.lessons, required this.statusColor, this.onEditLesson, this.editingLessonNumber});

  // Генерируем фиксированный цвет для каждого урока на основе его номера
  Color _getEditorColor(int lessonNumber) {
    if (editColors.isEmpty) return loadMax;
    return editColors[lessonNumber % editColors.length];
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: ps(h: 11.fw, v: 11.fh),
      decoration: BoxDecoration(color: white, borderRadius: BorderRadius.circular(12)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Шапка карточки
          Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(color: statusColor, borderRadius: BorderRadius.circular(5.r)),
                child: Center(
                  child: Text(
                    day,
                    style: TextStyle(fontFamily: 'Inter', fontSize: 12.fh, fontWeight: .w400, color: white),
                  ),
                ),
              ),
              SizedBox(width: 12.fw),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    month.toUpperCase(),
                    style: TextStyle(fontFamily: 'SF Pro', fontSize: 24.fh, fontWeight: .w700, color: statusColor),
                  ),
                  Text(
                    weekday,
                    style: TextStyle(fontFamily: 'SF Pro', fontSize: 15.fh, fontWeight: .w400, color: text),
                  ),
                ],
              ),
            ],
          ),
          SizedBox(height: 16.fh),
          // Список уроков
          if (lessons.isEmpty)
            Padding(
              padding: ps(v: 16.fh),
              child: Center(
                child: Text(
                  'Нет уроков на этот день',
                  style: TextStyle(fontFamily: 'SF Pro', fontSize: 14.fh, color: text),
                ),
              ),
            )
          else
            ...lessons.map((lesson) {
              final isEditing = (lesson.lessonNumber == editingLessonNumber) || lesson.isEditing;
              final hColor = _getEditorColor(lesson.lessonNumber);

              return Padding(
                padding: po(b: 16.fh),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Padding(
                          padding: po(t: 4.fh),
                          child: Text(
                            '${lesson.lessonNumber}. ',
                            style: TextStyle(fontFamily: 'Inter', fontSize: 14.fh, fontWeight: .w500, color: Color(0xff7D7D7D)),
                          ),
                        ),
                        Expanded(
                          child: Container(
                            padding: ps(v: 4.fh, h: 8.fw),
                            decoration: BoxDecoration(
                              color: isEditing ? hColor.withOpacity(0.6) : Colors.transparent,
                              border: isEditing
                                  ? Border(
                                      left: BorderSide(color: hColor, width: 2.fw),
                                      right: BorderSide(color: hColor, width: 2.fw),
                                    )
                                  : null,
                            ),
                            child: RichText(
                              text: TextSpan(
                                children: [
                                  TextSpan(
                                    text: '${lesson.subjectName}. ',
                                    style: TextStyle(fontFamily: 'Inter', fontSize: 14.fh, fontWeight: .w400, color: black),
                                  ),
                                  TextSpan(
                                    text: lesson.lessonType,
                                    style: TextStyle(fontFamily: 'SF Pro', fontSize: 14.fh, fontWeight: .w400, color: black),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                        SizedBox(width: 12.fw),
                        if (onEditLesson != null && lesson.isEditable)
                          GestureDetector(
                            onTap: () {
                              if (onEditLesson != null) onEditLesson!(lesson);
                            },
                            child: Container(
                              width: 26,
                              height: 26,
                              decoration: BoxDecoration(color: loadMax, borderRadius: BorderRadius.circular(4.r)),
                              child: Icon(Icons.edit_outlined, color: Colors.white, size: 18.fh),
                            ),
                          ),
                      ],
                    ),
                    // Плашка с ФИО того, кто редактирует
                    if (isEditing)
                      Row(
                        children: [
                          Spacer(),
                          Padding(
                            padding: ps(h: 30.fw),
                            child: Container(
                              decoration: BoxDecoration(color: hColor),
                              child: Text(
                                lesson.isEditing && lesson.editorName != null ? lesson.editorName! : lesson.teacherName,
                                style: TextStyle(fontFamily: 'SF Pro', fontSize: 8.fh, fontWeight: .w400, color: white),
                              ),
                            ),
                          ),
                        ],
                      ),
                    Padding(
                      padding: po(t: 8.fh),
                      child: Divider(color: text.withOpacity(0.3), height: 1),
                    ),
                  ],
                ),
              );
            }),
        ],
      ),
    );
  }
}
