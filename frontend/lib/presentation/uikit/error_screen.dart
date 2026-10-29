import 'package:flutter/material.dart';
import 'package:vize/vize.dart';
import 'colors.dart';

class ErrorScreen extends StatelessWidget {
  final int code;

  const ErrorScreen({super.key, required this.code});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: background,
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Icon(_getIcon(code), size: 50, color: black),
                Text(
                  _getTitle(code),
                  textAlign: TextAlign.start,
                  style: TextStyle(fontFamily: 'Inter', fontSize: 24, fontWeight: .w600, color: black),
                ),
              ],
            ),
            SizedBox(height: 14.fh),
            Text(
              _getDescription(code),
              textAlign: TextAlign.center,
              style: TextStyle(fontFamily: 'SF Pro', fontSize: 15, color: grey, fontWeight: .w400),
            ),

            SizedBox(height: 14.fh),
            Text(
              'ERROR CODE $code',
              style: TextStyle(fontFamily: 'SF Pro', fontSize: 10, color: text, fontWeight: .w600),
            ),
          ],
        ),
      ),
    );
  }

  IconData _getIcon(int code) {
    switch (code) {
      case 401:
        return Icons.no_accounts_outlined;
      case 403:
        return Icons.lock_outline;
      case 429:
        return Icons.timer_outlined;
      case 503:
        return Icons.build_outlined;
      default:
        return Icons.error_outline;
    }
  }
}

String _getTitle(int code) {
  switch (code) {
    case 401:
      return 'Мы не разговариваем\nс незнакомцами';
    case 403:
      return 'Доступ запрещен';
    case 429:
      return 'Кажется, теперь\nперегружены мы...';
    case 503:
      return 'Упс! Кажется что-то\nпошло не так...';
    default:
      return 'Упс! Кажется что-то\nпошло не так...';
  }
}

String _getDescription(int code) {
  switch (code) {
    case 401:
      return 'Мы не можем выдать доступ для\nнеавторизованных пользователей.\n\nПерезайдите в мини-приложение или\nвойдите в аккаунт для решения\nпроблемы.';
    case 403:
      return 'К сожалению, мы не нашли у Вас\nвысшее образование, так что доступ\nк ресурсу ограничен...\n\nЕсли такого не должно быть,\nобратитесь к администратору.';
    case 429:
      return 'К сервису поступает слишком\nмного запросов.\n\nПодождите некоторое время перед\nповторным взаимодействием с\nмини-приложением.';
    case 503:
      return 'Скорее всего сейчас проходят\nтехнические работы, так что мини-\nприложение может быть временно\nнедоступно';
    default:
      return 'Произошла непредвиденная ошибка.\nМы уже работаем над исправлением.';
  }
}
