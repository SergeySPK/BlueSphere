import 'package:flutter/cupertino.dart';

// Основные цвета проекта
const Color white = Color(0xffFFFFFF);
const Color black = Color(0xff000000);
const Color background = Color(0xffEAEAEA);
const Color text = Color(0xff99A2AD);
const Color bottomBarText = Color(0xff4B47B2);
const Color accent = Color(0xff7B16B9);
const Color classColor = Color(0xff3A3A3A);
const Color currentDayBorder = Color(0xff5882D7);
const Color emptyCell = Color(0xffE3E0EF);
const Color results = Color(0xffD9D9D9);

// Цвета загруженности
const Color loadMin = Color(0xffA7A3B5);
const Color loadLow = Color(0xff9585D0);
const Color loadMedium = Color(0xff6F55D0);
const Color loadHigh = Color(0xff5737CD);
const Color loadMax = Color(0xff3E288B);

// Палитра цветов для редактирования
const List<Color> editColors = [Color(0xFF4655DB), Color(0xFF46AFDB), Color(0xFF46DB78), Color(0xFFD9DB46), Color(0xFFDB9846), Color(0xFFDB4946), Color(0xFFDB4696), Color(0xFF7F46DB), Color(0xFF46DBA5), Color(0xFF7FDB46)];

// Функция для получения цвета по ID учителя
Color getTeacherColor(String teacherId) {
  if (teacherId.isEmpty) return editColors[0];
  final hash = teacherId.hashCode.abs();
  return editColors[hash % editColors.length];
}
