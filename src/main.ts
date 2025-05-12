import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { ConfigService } from './shared/infrastructure/config/config.service';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  const configService = app.get(ConfigService);

  const port = configService.getPort() || 3000;

  await app.listen(port);
  console.log(`Application is running on: http://localhost:${port}`);
}

bootstrap();
