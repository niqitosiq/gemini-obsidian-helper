import { Module, forwardRef } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { LlmProcessorService } from './application/services/llm-processor.service';
import { ToolsModule } from '../tools/tools.module';
import { GoogleGenaiAdapter } from './infrastructure/adapters/google-genai.adapter';
import { SharedModule } from '../../shared/shared.module';

@Module({
  imports: [forwardRef(() => ToolsModule), SharedModule],
  providers: [LlmProcessorService, GoogleGenaiAdapter],
  exports: [LlmProcessorService, GoogleGenaiAdapter],
})
export class LlmModule {}
