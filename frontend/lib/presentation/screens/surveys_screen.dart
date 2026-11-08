import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import '../../data/api_service.dart';
import '../../domain/survey.dart';
import '../../core/logger.dart';
import '../uikit/colors.dart';
import '../uikit/custom_header.dart';
import '../uikit/error_screen.dart';
import '../uikit/status_banner.dart';
import '../uikit/class_summary_card.dart';
import '../uikit/survey_results_card.dart';

// Экран с результатами опросов класса
class SurveysScreen extends StatefulWidget {
  final String classId;
  final String className;
  final VoidCallback onGoToClasses;

  const SurveysScreen({super.key, required this.classId, required this.className, required this.onGoToClasses});

  @override
  State<SurveysScreen> createState() => _SurveysScreenState();
}

class _SurveysScreenState extends State<SurveysScreen> {
  bool _isLoading = true;
  int? _errorCode;
  String _surveyDate = '';
  List<SurveyQuestionResult> _surveyQuestions = [];
  int? _bannerLevel;
  String? _bannerDate;

  bool get isClassSelected => widget.classId.isNotEmpty && widget.classId != 'Выберите класс';

  @override
  void initState() {
    super.initState();
    if (isClassSelected) {
      _loadData();
    } else {
      _isLoading = false;
    }
  }

  @override
  void didUpdateWidget(covariant SurveysScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.classId != widget.classId) {
      if (isClassSelected) {
        setState(() => _isLoading = true);
        _loadData();
      } else {
        setState(() => _isLoading = false);
      }
    }
  }

  // Загрузка списка опросов и статистики
  Future<void> _loadData() async {
    setState(() {
      _isLoading = true;
      _errorCode = null;
    });

    AppLogger.info('Начало загрузки данных для опросов (класс: ${widget.classId})', tag: '[UI] Surveys');

    try {
      final surveys = await ApiService.getClassSurveys(widget.classId);
      if (surveys.isEmpty) {
        AppLogger.info('Список опросов пуст', tag: '[UI] Surveys');
        if (mounted) setState(() => _isLoading = false);
        return;
      }

      final date = surveys[0]['survey_date'];
      _surveyDate = date;
      AppLogger.info('Выбран последний опрос на дату: $date', tag: '[UI] Surveys');

      try {
        final summary = await ApiService.getSummary(widget.classId, date);
        _bannerLevel = summary.hasData ? summary.level : 4;
        _bannerDate = summary.date;
        AppLogger.info('Баннер загружен: level=$_bannerLevel', tag: '[UI] Surveys');
      } catch (e) {
        _bannerLevel = 4;
        _bannerDate = date;
        AppLogger.error('Не удалось загрузить баннер', error: e, tag: '[UI] Surveys');
      }

      final stats = await ApiService.getSurveyStatistics(widget.classId, date);
      _parseStatistics(stats);

      if (mounted) setState(() => _isLoading = false);
    } catch (e) {
      int code = 500;
      final errorString = e.toString();
      if (errorString.contains('Exception: ')) {
        code = int.tryParse(errorString.split('Exception: ')[1]) ?? 500;
      }

      AppLogger.error('Ошибка загрузки данных опросов', error: e, tag: '[UI] Surveys');

      if (mounted) {
        setState(() {
          _errorCode = code;
          _isLoading = false;
        });
      }
    }
  }

  // Парсинг статистики в новую динамическую модель
  void _parseStatistics(Map<String, dynamic> stats) {
    final rawQuestions = stats['questions'] as List? ?? [];

    _surveyQuestions = rawQuestions.map((rawQuestion) {
      final question = Map<String, dynamic>.from(rawQuestion as Map);
      final rawOptions = question['options'] as List? ?? [];

      final options = rawOptions.map((rawOption) {
        final option = Map<String, dynamic>.from(rawOption as Map);
        final percentageValue = option['percentage'];
        final percentage = percentageValue is num ? percentageValue.round() : 0;

        return SurveyResultItem(label: (option['title'] ?? 'Без названия').toString(), percentage: percentage, isHighlighted: percentage > 50);
      }).toList();

      return SurveyQuestionResult(title: (question['title'] ?? 'Без названия').toString(), options: options);
    }).toList();
  }

  // Строим сводку для всех вопросов, кроме первого
  List<SurveyQuestionSummary> _buildQuestionSummaries() {
    if (_surveyQuestions.length <= 1) return [];
    return _surveyQuestions.asMap().entries.skip(1).map((entry) {
      final index = entry.key;
      final question = entry.value;

      String displayTitle = '';
      if (index == 1) {
        displayTitle = 'Самый тревожный урок на сегодня:';
      } else if (index == 2) {
        displayTitle = 'Самый легкий урок на сегодня:';
      } else if (index == 3) {
        displayTitle = 'Оценка интереса учащихся в сегодняшних уроках';
      } else {
        displayTitle = question.title;
      }

      if (question.options.isEmpty) {
        return SurveyQuestionSummary(title: displayTitle, topAnswer: 'Нет ответов');
      }

      final top = question.options.reduce((a, b) => a.percentage > b.percentage ? a : b);
      return SurveyQuestionSummary(title: displayTitle, topAnswer: top.percentage > 0 ? top.label : 'Нет ответов');
    }).toList();
  }

  // Получение текстового статуса для главного круга
  String _getGeneralStatus() {
    if (_surveyQuestions.isEmpty || _surveyQuestions.first.options.isEmpty) return 'НЕТ ДАННЫХ';
    final top = _surveyQuestions.first.options.reduce((a, b) => a.percentage > b.percentage ? a : b);
    if (top.percentage == 0) return 'НЕТ ДАННЫХ';
    final label = top.label.toLowerCase();
    if (label.contains('отлично')) return 'ОТЛИЧНО';
    if (label.contains('хорошо')) return 'ХОРОШО';
    if (label.contains('удовлетворительно') && !label.contains('не')) return 'УДОВЛЕТВОРИТЕЛЬНО';
    if (label.contains('неудовлетворительно')) return 'НЕУДОВЛЕТВОРИТЕЛЬНО';
    if (label.contains('плохо')) return 'ПЛОХО';
    return top.label.toUpperCase();
  }

  // Получение процента для главного круга
  int _getTopPercentage() {
    if (_surveyQuestions.isEmpty || _surveyQuestions.first.options.isEmpty) return 0;
    return _surveyQuestions.first.options.reduce((a, b) => a.percentage > b.percentage ? a : b).percentage;
  }

  // Форматирование даты
  String _formatDate(String isoDate) {
    if (isoDate.isEmpty) return '';
    if (isoDate.contains('.')) return isoDate;
    try {
      final parts = isoDate.split('-');
      if (parts.length == 3) {
        final month = int.parse(parts[1]);
        final day = int.parse(parts[2]);
        return '${day.toString().padLeft(2, '0')}.${month.toString().padLeft(2, '0')}';
      }
    } catch (e) {}
    return isoDate;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: background,
      body: Column(
        children: [
          GestureDetector(
            onTap: widget.onGoToClasses,
            child: CustomHeader(title: isClassSelected ? 'Класс ${widget.className}' : 'Выберите класс'),
          ),
          Expanded(
            child: _errorCode != null
                ? ErrorScreen(code: _errorCode!)
                : !isClassSelected
                ? _buildNoClassSelected()
                : _isLoading
                ? Center(child: CircularProgressIndicator(color: loadMax))
                : _surveyQuestions.isEmpty
                ? Center(
                    child: Text(
                      'Нет данных об опросах',
                      style: TextStyle(fontFamily: 'SF Pro', color: text),
                    ),
                  )
                : SingleChildScrollView(
                    padding: po(t: 8.fh, l: 16.fw, r: 16.fw),
                    child: Column(
                      children: [
                        if (_bannerLevel != null) ...[StatusBanner(level: _bannerLevel!, date: _formatDate(_bannerDate ?? _surveyDate), showButton: false), SizedBox(height: 11.fh)],
                        ClassSummaryCard(date: _formatDate(_surveyDate), percentage: _getTopPercentage(), statusText: _getGeneralStatus(), questionSummaries: _buildQuestionSummaries()),
                        SizedBox(height: 11.fh),
                        SurveyResultsCard(date: _formatDate(_surveyDate), questions: _surveyQuestions),
                      ],
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildNoClassSelected() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            'Класс не выбран',
            style: TextStyle(fontFamily: 'Inter', fontSize: 18.fh, fontWeight: .w600, color: black),
          ),
          SizedBox(height: 8.fh),
          Text(
            'Чтобы посмотреть опросы,\nвыберите класс',
            textAlign: TextAlign.center,
            style: TextStyle(fontFamily: 'SF Pro', fontSize: 14.fh, fontWeight: .w400, color: text),
          ),
          SizedBox(height: 24.fh),
          ElevatedButton(
            onPressed: widget.onGoToClasses,
            style: ElevatedButton.styleFrom(
              backgroundColor: bottomBarText,
              padding: ps(h: 24.fw, v: 12.fh),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12.r)),
            ),
            child: Text(
              'Перейти к классам',
              style: TextStyle(fontFamily: 'Inter', fontSize: 14.fh, fontWeight: .w500, color: white),
            ),
          ),
        ],
      ),
    );
  }
}
