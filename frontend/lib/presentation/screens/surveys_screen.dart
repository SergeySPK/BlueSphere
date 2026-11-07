import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import '../../data/api_service.dart';
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
  List<SurveyResultItem> _generalResults = [];
  List<SurveyResultItem> _stressSubjects = [];
  List<SurveyResultItem> _easySubjects = [];
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

  // Загрузка списка опросов и статистики по последнему из них
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

      final latestSurvey = surveys[0];
      final date = latestSurvey['survey_date'];
      _surveyDate = date;
      AppLogger.info('Выбран последний опрос на дату: $date', tag: '[UI] Surveys');

      try {
        final summary = await ApiService.getSummary(widget.classId, date);
        _bannerLevel = summary.hasData ? summary.level : 4;
        _bannerDate = summary.date;
        AppLogger.info('Баннер для опроса: level=$_bannerLevel, hasData=${summary.hasData}', tag: '[UI] Surveys');
      } catch (e) {
        _bannerLevel = 4;
        _bannerDate = date;
        AppLogger.error('Не удалось загрузить баннер для опроса', error: e, tag: '[UI] Surveys');
      }

      final stats = await ApiService.getSurveyStatistics(widget.classId, date);
      _parseStatistics(stats);

      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
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

  // Парсинг статистики из JSON в списки для UI
  void _parseStatistics(Map<String, dynamic> stats) {
    final questions = stats['questions'] as List? ?? [];

    _generalResults.clear();
    _stressSubjects.clear();
    _easySubjects.clear();

    for (var q in questions) {
      final title = (q['title'] ?? '').toString().toLowerCase();
      final options = q['options'] as List? ?? [];

      final parsedOptions = options.map((opt) {
        final optTitle = opt['title'] ?? 'Без названия';
        final percent = (opt['percentage'] ?? 0).toInt();

        return SurveyResultItem(label: optTitle, percentage: percent, isHighlighted: percent > 50);
      }).toList();

      // Распределяем вопросы по категориям
      if (title.contains('общая оценка') || title.contains('состояние')) {
        _generalResults = parsedOptions;
      } else if (title.contains('тревожно') || title.contains('стресс') || title.contains('сложн')) {
        _stressSubjects = parsedOptions;
      } else if (title.contains('легко') || title.contains('просто')) {
        _easySubjects = parsedOptions;
      }
    }
  }

  // Получение самого частого ответа
  String _getTopSubject(List<SurveyResultItem> items) {
    if (items.isEmpty) return 'Нет данных';
    final top = items.reduce((a, b) => a.percentage > b.percentage ? a : b);
    return top.percentage > 0 ? top.label : 'Нет ответов';
  }

  // Получение текстового статуса
  String _getGeneralStatus() {
    if (_generalResults.isEmpty) return 'НЕТ ДАННЫХ';
    final top = _generalResults.reduce((a, b) => a.percentage > b.percentage ? a : b);
    if (top.percentage == 0) return 'НЕТ ДАННЫХ';

    final label = top.label.toLowerCase();
    if (label.contains('отлично')) return 'ОТЛИЧНОЕ СОСТОЯНИЕ';
    if (label.contains('хорошо')) return 'ХОРОШЕЕ СОСТОЯНИЕ';
    if (label.contains('удовлетворительно') && !label.contains('не')) return 'УДОВЛЕТВОРИТЕЛЬНОЕ СОСТОЯНИЕ';
    if (label.contains('неудовлетворительно')) return 'НЕУДОВЛЕТВОРИТЕЛЬНОЕ СОСТОЯНИЕ';
    if (label.contains('плохо')) return 'ПЛОХОЕ СОСТОЯНИЕ';

    return '${top.label.toUpperCase()} СОСТОЯНИЕ';
  }

  int _getTopPercentage(List<SurveyResultItem> items) {
    if (items.isEmpty) return 0;
    return items.reduce((a, b) => a.percentage > b.percentage ? a : b).percentage;
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
                : _generalResults.isEmpty && _stressSubjects.isEmpty && _easySubjects.isEmpty
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
                        ClassSummaryCard(
                          date: _formatDate(_surveyDate),
                          percentage: _getTopPercentage(_generalResults),
                          statusText: _getGeneralStatus(),
                          hardestSubject: _getTopSubject(_stressSubjects),
                          easiestSubject: _getTopSubject(_easySubjects),
                        ),
                        SizedBox(height: 11.fh),
                        SurveyResultsCard(date: _formatDate(_surveyDate), generalResults: _generalResults, stressSubjects: _stressSubjects, easySubjects: _easySubjects),
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
